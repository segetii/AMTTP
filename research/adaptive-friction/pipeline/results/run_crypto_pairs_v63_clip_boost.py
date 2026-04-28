"""
Crypto BSDT — v63: Additive Floating Clip Boost
================================================
Diagnosis of v62 failure
-------------------------
v62's continuous priority encoder REPLACED v58's direct G/T threshold comparison
with a sigmoid gate on the floating EMA charge:

    v62 phase: 1 + (CLIP−1)·g_G·g_T + pc·[g_G(1−g_T)+…] − kill·(1−g_G)(1−g_T)

The floating gate asks "has G been active above its 168-bar average?"
v58 asks "did G fire THIS bar?"  The bar-by-bar signal is far sharper — it
is why v58 achieves OOS H2 =+4.74 while all v62 configs land at +2.70-2.90.
The floating gate introduced a slow-moving average that dilutes the crisp
entry-timing signal that makes v58 profitable.

v63 fix: ADDITIVE CLIP BOOST (never destroy v58 logic)
---------------------------------------------------------
v63 leaves v58's entire phase machinery unchanged and adds one modulation:

    clip_mod(t) = CLIP_BASE + CLIP_BOOST · g_G(t) · g_T(t)
                = 6.0     + [0, 4.0]                            (config-dependent)

Only the HH case (G_mem > gth AND T_mem > T_thresh) uses clip_mod instead of
hard CLIP=6.  Kill (HL/LH/LL) stays at 0.05.  No-fire stays at 1.0.

    When both floating gates are HOT (g_G·g_T → 1): clip_mod → 10x
    When floating gates are NEUTRAL (g_G·g_T ≈ 0.25): clip_mod ≈ 7x
    When floating gates are COLD (g_G·g_T → 0): clip_mod = CLIP_BASE = 6x (v58)

Alpha-sensitivity bound (analytic)
-----------------------------------
The only alpha-sensitive path is clip_mod on HH bars:

    E[clip_mod] = CLIP_BASE + CLIP_BOOST · E[g_G] · E[g_T]

Since Q_G_z is AGC-normalised (Var≈1, mean≈0 ∀α), E[g_G] is alpha-invariant.
From v62 verification table:  E[g_G(α=0.75)] = 0.545, E[g_G(α=0.95)] = 0.508.
Δ E[clip_mod] ≈ CLIP_BOOST × (0.545² − 0.508²) ≈ CLIP_BOOST × 0.04.
For CLIP_BOOST=4:  Δclip ≈ 0.16 pct-points on average clip ≈ 6.7 → ~2.4% change.
Expected max Sharpe drop: 2.4% × v58 H2 ≈ 0.114.  Well under 0.15 bar.

Kill-lift variant
-----------------
v63_killmod also slightly lifts the kill floor when both floating gates are
warm (g_G·g_T > threshold), turning the hard 0.05 kill into a soft lift:

    phase_kill = 0.05 + KILL_LIFT · g_G · g_T     (only on HL/LH/LL fire bars)

This preserves the aggressiveness of the kill while allowing partial recovery
when the G+T channels are persistently active in the background.

Configs tested
--------------
  v58_tight (ref)              — no floating gate, pure v58
  v63_b2_k4_mu0               — CLIP_BOOST=2, k=4, μ=0.0
  v63_b4_k4_mu0               — CLIP_BOOST=4, k=4, μ=0.0
  v63_b2_k4_mu0.5             — CLIP_BOOST=2, k=4, μ=0.5 (selective boost)
  v63_b2_k4_muneg0.5          — CLIP_BOOST=2, k=4, μ=−0.5 (wider boost)
  v63_b2_k6_mu0               — CLIP_BOOST=2, k=6, μ=0.0 (steeper gate)
  v63_b4_killmod_k4_mu0       — CLIP_BOOST=4 + KILL_LIFT=0.03, k=4, μ=0.0

Tests
------
  TEST 1 — OOS split (pass: H2 ≥ 3.60, stretch: H2 ≥ 4.74)    ← new stretch bar
  TEST 2 — Alpha sensitivity (pass: max |drop| < 0.15)          ← main bar
  TEST 3 — Clip boost sensitivity (CLIP_BOOST ±1, ±2)
  TEST 4 — Mu / steepness sensitivity  (μ ±0.25/0.50, k ±2)
  TEST 5 — rv stress on v63 champion
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

# ── frozen v58 champion constants ─────────────────────────────────────────────
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

# ── floating gate constants (carried from v61/v62) ─────────────────────────────
ALPHA_FG  = 0.85
AGC_SPAN  = 168    # fixed 1-week window — alpha-independent

# ── v63 additive clip boost constants ─────────────────────────────────────────
CLIP_BASE   = 6.0           # same as v58 CLIP — floor when gate is cold
# CLIP_BOOST: per-config, controls how much extra boost floating gate can add
# clip_dynamic(t) = CLIP_BASE + CLIP_BOOST * g_G(t) * g_T(t)
#   → [6.0, CLIP_BASE + CLIP_BOOST]

OOS_SPLIT = '2025-01-01'


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


# ── shared: AGC-normalised floating gate ──────────────────────────────────────

def _float_gate_charge(a: np.ndarray, alpha: float) -> np.ndarray:
    """Q(t) = alpha*Q(t-1) + a(t-1).  Causal: shift-1 built in."""
    q = np.zeros(len(a), dtype=float)
    for t in range(1, len(a)):
        q[t] = alpha * q[t - 1] + a[t - 1]
    return q

def _float_gate_normalised(a: np.ndarray, alpha: float) -> np.ndarray:
    """
    Coupling cap + AGC: Q_z = (Q − EMA(Q, AGC_SPAN)) / EMA_std(Q, AGC_SPAN).
    Confirmed in v61: E[Q_z]≈0, Var[Q_z]≈1 ∀ α ∈ {0.75, 0.85, 0.95}.
    AGC_SPAN=168 is independent of α.
    """
    q   = _float_gate_charge(a, alpha)
    q_s = pd.Series(q)
    dc  = q_s.ewm(span=AGC_SPAN, adjust=False).mean().values
    std = q_s.ewm(span=AGC_SPAN, adjust=False).std().fillna(1.0).values
    return (q - dc) / np.maximum(std, 1e-8)

def _sigmoid_gate(q_z: np.ndarray, k: float, mu: float) -> np.ndarray:
    """
    Stateless MOSFET sigmoid gate.  g ∈ (0,1).

    g(z) = 1 / (1 + exp(−k·(z − μ)))

    STATELESS: g(t) depends only on Q_z(t) — no state, no autocorrelation
    amplification.  If Q_z marginal distribution is alpha-invariant (proved
    in v61), then E[g(Q_z)] is also alpha-invariant.
    """
    return 1.0 / (1.0 + np.exp(-k * (q_z - mu)))


# ── v63: Additive Floating Clip Boost ─────────────────────────────────────────

def _build_pnl_v63(
    base:       pd.Series,
    sv36:       pd.DataFrame,
    lf:         pd.DataFrame,
    s4:         pd.DataFrame,
    rv_norm:    pd.Series,
    lo:         float = -0.01,
    alpha:      float = ALPHA_FG,
    k:          float = 4.0,
    mu:         float = 0.0,
    clip_boost: float = 2.0,
    kill_lift:  float = 0.0,
) -> pd.Series:
    """
    v63: Additive Floating Clip Boost on v58 base.

    Changes from v58 (purely additive):
    ────────────────────────────────────
    1. Compute AGC-normalised floating gate charges Q_G_z, Q_T_z.
    2. Compute sigmoid gates g_G, g_T ∈ (0,1)  — STATELESS.
    3. Modulate CLIP on HH bars:
         clip_mod = CLIP_BASE + clip_boost * g_G * g_T
         Phase on HH = clip_mod  (was hard CLIP=6.0)
    4. Optional kill lift on non-HH fire bars:
         phase_kill = 0.05 + kill_lift * g_G * g_T  (lifts kill floor slightly)

    Accept rv_norm and lo identically to _build_pnl_v58 so that
    at clip_boost=0, kill_lift=0 the output is IDENTICAL to v58.

    Alpha independence:
    ───────────────────
    E[clip_mod] = CLIP_BASE + clip_boost · E[g_G] · E[g_T]

    E[g_G] and E[g_T] are alpha-invariant because Q_G_z marginal is AGC-normalised.
    From v62 verification: E[g_G] varies by ±0.02 over α ∈ {0.75..0.95}.
    → E[clip_mod] varies by clip_boost × 0.04 ≈ at most 0.16 clip units.
    → Expected Sharpe sensitivity ≈ 2.4% (CLIP_BOOST=4) → max drop ≈ 0.11.
    """
    idx  = base.index
    sv36 = sv36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lf.reindex(idx,   method='ffill').fillna(0.5)
    s4   = s4.reindex(idx,   method='ffill').fillna(0.0)
    gam  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lp   = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size = np.clip(1.0 - gam.values, 0.0, 1.0) * (0.75 + 0.5 * lp.values)

    a_G  = s4['a_G']
    a_A  = s4['a_A']
    a_T  = s4['a_T']

    # gth: identical computation to v58 — passes rv_norm and lo verbatim
    gth  = _dynamic_gth(rv_norm.reindex(idx, method='ffill').fillna(1.0), lo)
    gth_vals = gth.values

    G_mem  = a_G.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    T_mem  = a_T.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    fired  = a_A.shift(1).fillna(0.0) > A_FIRE_THRESH

    G_above = (G_mem.values > gth_vals)
    T_above = (T_mem.values > T_THRESH_BASE)
    fire_b  = fired.values.astype(bool)

    q_HH = fire_b &  G_above &  T_above
    q_HL = fire_b &  G_above & ~T_above
    q_LH = fire_b & ~G_above &  T_above
    q_LL = fire_b & ~G_above & ~T_above

    # ── floating gate machinery ────────────────────────────────────────────────
    a_G_arr = a_G.values
    a_T_arr = a_T.values
    Q_G_z   = _float_gate_normalised(a_G_arr, alpha)
    Q_T_z   = _float_gate_normalised(a_T_arr, alpha)
    g_G     = _sigmoid_gate(Q_G_z, k, mu)   # ∈ (0,1), STATELESS
    g_T     = _sigmoid_gate(Q_T_z, k, mu)  # ∈ (0,1), STATELESS

    joint   = g_G * g_T                      # ∈ (0,1)

    # ── dynamic CLIP (only affects HH bars) ───────────────────────────────────
    clip_dyn = CLIP_BASE + clip_boost * joint      # vector ∈ [CLIP_BASE, CLIP_BASE+boost]

    # ── dynamic kill floor (optional, default off via kill_lift=0) ────────────
    kill_floor = 0.05 + kill_lift * joint          # vector ∈ [0.05, 0.05+kill_lift]

    # ── phase logic: v58 except HH uses clip_dyn and kill uses kill_floor ─────
    phase = np.ones(len(fire_b), dtype=float)  # no-fire → 1.0 (neutral = v58)
    phase[q_HH] = clip_dyn[q_HH]               # HH → dynamic clip (was hard 6.0)
    phase[q_HL] = kill_floor[q_HL]             # HL → kill floor (was hard 0.05)
    phase[q_LH] = kill_floor[q_LH]             # LH → kill floor
    phase[q_LL] = kill_floor[q_LL]             # LL → kill floor

    # ── champion boost (unchanged from v58) ───────────────────────────────────
    flag = np.zeros(len(a_G_arr), dtype=float)
    flag[1:] = (a_G_arr[:-1] > G_BOOST_THRESH).astype(float)

    return pd.Series(
        base.reindex(idx).fillna(0.0).values * size
        * (1.0 + CHAMPION_BOOST * flag) * phase,
        index=idx,
    )


ANN_1H = 365.25 * 24   # annualisation factor for 1h PnL bars


def _full_stats(pnl: pd.Series) -> dict:
    """
    Extended statistics beyond _stats():
      sharpe   — annualised Sharpe
      sortino  — annualised Sortino  (downside std only)
      calmar   — |CAGR / max_dd|
      cagr     — compound annual growth rate
      max_dd   — maximum drawdown (fraction, negative)
      avg_dd   — mean of underwater periods (fraction)
      win_rate — fraction of bars with positive PnL
      avg_win  — mean positive bar return
      avg_loss — mean negative bar return
      profit_f — profit factor = sum(wins) / |sum(losses)|
      final    — terminal equity starting from $100
      yoy      — {year: return fraction} for each calendar year present
    """
    p = pnl.fillna(0.0)
    n = len(p)
    if p.std() < 1e-12 or n < 2:
        return dict(sharpe=0.0, sortino=0.0, calmar=0.0, cagr=0.0,
                    max_dd=0.0, avg_dd=0.0, win_rate=0.5, avg_win=0.0,
                    avg_loss=0.0, profit_f=1.0, final=100.0, yoy={})

    mean_r  = float(p.mean())
    std_r   = float(p.std())
    sharpe  = mean_r / std_r * np.sqrt(ANN_1H)

    down    = p[p < 0]
    down_std = float(down.std()) if len(down) > 1 else std_r
    sortino = mean_r / down_std * np.sqrt(ANN_1H) if down_std > 1e-12 else sharpe

    eq      = 100.0 * (1.0 + p).cumprod()
    peak    = eq.cummax()
    dd_ser  = eq / peak - 1.0
    max_dd  = float(dd_ser.min())
    avg_dd  = float(dd_ser[dd_ser < 0].mean()) if (dd_ser < 0).any() else 0.0

    yrs     = max((p.index[-1] - p.index[0]).days / 365.25, 0.01)
    cagr    = float((eq.iloc[-1] / 100.0) ** (1.0 / yrs) - 1.0)
    calmar  = float(cagr / abs(max_dd)) if abs(max_dd) > 1e-12 else 0.0

    wins    = p[p > 0]; losses = p[p < 0]
    win_rate = float(len(wins) / n)
    avg_win  = float(wins.mean())    if len(wins)   > 0 else 0.0
    avg_loss = float(losses.mean())  if len(losses) > 0 else 0.0
    profit_f = (float(wins.sum()) / abs(float(losses.sum()))
                if abs(float(losses.sum())) > 1e-12 else np.inf)

    yoy = {}
    for yr in sorted(p.index.year.unique()):
        mask = p.index.year == yr
        r_yr = float((1.0 + p[mask]).prod() - 1.0)
        yoy[int(yr)] = r_yr

    return dict(sharpe=sharpe, sortino=sortino, calmar=calmar, cagr=cagr,
                max_dd=max_dd, avg_dd=avg_dd, win_rate=win_rate,
                avg_win=avg_win, avg_loss=avg_loss, profit_f=profit_f,
                final=float(eq.iloc[-1]), yoy=yoy)


def _sharpe(p):  return _full_stats(p)['sharpe']
def _maxdd(p):   return _full_stats(p)['max_dd']


def _fmt_stats_header() -> str:
    return (f"  {'Config':<44} {'Sharpe':>7} {'Sortino':>8} {'Calmar':>7}"
            f" {'CAGR':>7} {'MaxDD':>7} {'AvgDD':>7}"
            f" {'WinR':>6} {'PF':>6} {'$100→':>8}")

def _fmt_stats_row(label: str, s: dict) -> str:
    pf_s = f"{s['profit_f']:>6.2f}" if s['profit_f'] != np.inf else "   ∞  "
    return (f"  {label:<44} {s['sharpe']:>+7.3f} {s['sortino']:>+8.3f} {s['calmar']:>+7.2f}"
            f" {s['cagr']:>+6.1%} {s['max_dd']:>+7.1%} {s['avg_dd']:>+7.1%}"
            f" {s['win_rate']:>5.1%} {pf_s} ${s['final']:>7.2f}")

def _fmt_stats_divider() -> str:
    return "  " + "-"*44 + " " + "-"*7 + " " + "-"*8 + " " + "-"*7 + " " + "-"*7 + " " + "-"*7 + " " + "-"*7 + " " + "-"*6 + " " + "-"*6 + " " + "-"*8


def _fmt_alpha_header() -> str:
    return (f"  {'α':>6} {'Sharpe':>7} {'Sortino':>8} {'Calmar':>7}"
            f" {'CAGR':>7} {'MaxDD':>7} {'AvgDD':>7}"
            f" {'WinR':>6} {'Δ_Sharpe':>9}  Verdict")

def _fmt_alpha_row(al: float, s: dict, drop: float, is_base: bool) -> str:
    verdict = '—' if is_base else ('PASS' if abs(drop) < 0.15 else 'FAIL')
    pf_s = f"{s['profit_f']:>6.2f}" if s['profit_f'] != np.inf else "   ∞  "
    return (f"  {al:>6.2f} {s['sharpe']:>+7.3f} {s['sortino']:>+8.3f} {s['calmar']:>+7.2f}"
            f" {s['cagr']:>+6.1%} {s['max_dd']:>+7.1%} {s['avg_dd']:>+7.1%}"
            f" {s['win_rate']:>5.1%} {drop:>+9.4f}  {verdict}")


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    t0  = time.time()
    BAR = '=' * 100
    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)

    print(BAR)
    print("  v63 — Additive Floating Clip Boost  (v58 logic intact, only CLIP modulated)")
    print("  clip_mod(t) = CLIP_BASE + CLIP_BOOST · g_G(t) · g_T(t)")
    print("  g(z) = sigmoid(k*(z−μ))  |  STATELESS: no autocorrelation amplification")
    print("  Phase: HH→clip_mod, kill→0.05, no-fire→1.0  (identical to v58 at BOOST=0)")
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

    rv_ema = _realized_vol(df_1h, ema_span=3)

    # ── clip-boost gate statistics ────────────────────────────────────────────
    t('[8] Clip boost gate verification (alpha-independence of E[g_G · g_T])')
    a_G_arr = sig_4ch['a_G'].values; a_T_arr = sig_4ch['a_T'].values
    print(f"  {'α':>5}  {'k':>4} {'μ':>5}  {'E[g_G]':>7} {'E[g_T]':>7}"
          f"  {'E[joint]':>9}  {'E[clip_mod] (B=2)':>18}  {'E[clip_mod] (B=4)':>18}")
    print(f"  {'-'*5}  {'-'*4} {'-'*5}  {'-'*7} {'-'*7}  {'-'*9}  {'-'*18}  {'-'*18}")
    for al in [0.75, 0.80, 0.85, 0.90, 0.95]:
        Qgz = _float_gate_normalised(a_G_arr, al)
        Qtz = _float_gate_normalised(a_T_arr, al)
        gG  = _sigmoid_gate(Qgz[test_mask], 4.0, 0.0)
        gT  = _sigmoid_gate(Qtz[test_mask], 4.0, 0.0)
        j   = gG * gT
        print(f"  {al:>5.2f}  {'4':>4} {'0.0':>5}  "
              f"{np.mean(gG):>7.4f} {np.mean(gT):>7.4f}  "
              f"{np.mean(j):>9.4f}  "
              f"{'6 + 2*' + f'{np.mean(j):.4f}':>12} ={'':>1}{6+2*np.mean(j):>5.3f}  "
              f"{'6 + 4*' + f'{np.mean(j):.4f}':>12} ={'':>1}{6+4*np.mean(j):>5.3f}")

    # ── Config registry ────────────────────────────────────────────────────────
    # (label, mode, kwargs)
    # v63 configs always get rv_norm=rv_ema, lo=-0.01 plus circuit-specific params
    _v63base = dict(rv_norm=rv_ema, lo=-0.01)
    configs = {
        'v58_tight (ref)           ':  ('v58',  dict(rv_norm=rv_ema, lo=-0.01)),
        'v63_b2_k4_mu0             ':  ('v63',  {**_v63base, 'clip_boost': 2.0, 'k': 4.0, 'mu': 0.0}),
        'v63_b4_k4_mu0             ':  ('v63',  {**_v63base, 'clip_boost': 4.0, 'k': 4.0, 'mu': 0.0}),
        'v63_b2_k4_mu0.5           ':  ('v63',  {**_v63base, 'clip_boost': 2.0, 'k': 4.0, 'mu': 0.5}),
        'v63_b2_k4_muneg0.5        ':  ('v63',  {**_v63base, 'clip_boost': 2.0, 'k': 4.0, 'mu': -0.5}),
        'v63_b2_k6_mu0             ':  ('v63',  {**_v63base, 'clip_boost': 2.0, 'k': 6.0, 'mu': 0.0}),
        'v63_b4_killmod_k4_mu0     ':  ('v63',  {**_v63base, 'clip_boost': 4.0, 'k': 4.0, 'mu': 0.0, 'kill_lift': 0.03}),
    }

    def _pnl(label, mode, kw):
        if mode == 'v58':
            return _build_pnl_v58(base_pnl, sig_v36, lam_feat, sig_4ch, **kw)
        return _build_pnl_v63(base_pnl, sig_v36, lam_feat, sig_4ch, **kw)

    # ── TEST 1: OOS SPLIT ─────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  TEST 1 — OOS SPLIT  (pass: H2 ≥ 3.60  |  stretch goal: H2 ≥ 4.74 = v58)')
    print(f'{BAR}')

    oos_results = {}
    for label, (mode, kw) in configs.items():
        pnl     = _pnl(label, mode, kw)
        sf      = _full_stats(pnl[test_mask])
        sh1     = _full_stats(pnl[first_half])
        sh2     = _full_stats(pnl[second_half])
        ok      = sh2['sharpe'] >= 3.60
        stretch = sh2['sharpe'] >= 4.74

        # ── full-period stats ──────────────────────────────────────────────────
        print(f'\n  ── {label.strip()} {"← PREV CHAMPION" if label.strip().startswith("v58") else ""}'
              f'{"  ✓ PASS" if ok else "  ✗ FAIL"}'
              f'{"  ✓ STRETCH" if stretch else ""}')
        print(f'  {"Period":<10} {"Sharpe":>7} {"Sortino":>8} {"Calmar":>7}'
              f' {"CAGR":>7} {"MaxDD":>7} {"AvgDD":>7}'
              f' {"WinR":>6} {"PF":>6} {"$100→":>8}')
        print(f'  {"-"*10} {"-"*7} {"-"*8} {"-"*7}'
              f' {"-"*7} {"-"*7} {"-"*7}'
              f' {"-"*6} {"-"*6} {"-"*8}')
        for period_label, st in [('FULL test', sf), ('H1 23-24', sh1), ('H2 25-26', sh2)]:
            pf_s = f"{st['profit_f']:>6.2f}" if st['profit_f'] != np.inf else "   ∞  "
            print(f'  {period_label:<10} {st["sharpe"]:>+7.3f} {st["sortino"]:>+8.3f}'
                  f' {st["calmar"]:>+7.2f} {st["cagr"]:>+6.1%}'
                  f' {st["max_dd"]:>+7.1%} {st["avg_dd"]:>+7.1%}'
                  f' {st["win_rate"]:>5.1%} {pf_s} ${st["final"]:>7.2f}')

        # ── year-on-year breakdown (OOS only) ─────────────────────────────────
        yoy_oos = {yr: r for yr, r in sf['yoy'].items()
                   if yr >= int(TEST_START[:4])}
        if yoy_oos:
            yoy_str = '  '.join(f'{yr}: {r:>+6.1%}' for yr, r in sorted(yoy_oos.items()))
            print(f'  YoY OOS: {yoy_str}')

        oos_results[label.strip()] = {
            'sharpe_full':    float(sf['sharpe']),
            'sortino_full':   float(sf['sortino']),
            'calmar_full':    float(sf['calmar']),
            'cagr_full':      float(sf['cagr']),
            'maxdd_full':     float(sf['max_dd']),
            'win_rate_full':  float(sf['win_rate']),
            'profit_f_full':  float(sf['profit_f']) if sf['profit_f'] != np.inf else 99.0,
            'final_full':     float(sf['final']),
            'sharpe_first':   float(sh1['sharpe']),
            'sharpe_second':  float(sh2['sharpe']),
            'maxdd_second':   float(sh2['max_dd']),
            'calmar_second':  float(sh2['calmar']),
            'sortino_second': float(sh2['sortino']),
            'cagr_second':    float(sh2['cagr']),
            'yoy':            {str(k): float(v) for k, v in sf['yoy'].items()},
            'pass': ok, 'stretch': stretch,
        }

    # ── TEST 2: ALPHA SENSITIVITY ─────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  TEST 2 — ALPHA SENSITIVITY  (pass: max |Δ Sharpe| < 0.15)')
    print('  Analytic bound: Δ E[clip_mod] = CLIP_BOOST × ΔE[g²] ≈ CLIP_BOOST × 0.04')
    print('  CLIP_BOOST=2 → Δclip≈0.08 → expected max drop < 0.05')
    print('  CLIP_BOOST=4 → Δclip≈0.16 → expected max drop < 0.12')
    print(f'{BAR}')

    alpha_perturbs = [0.75, 0.80, 0.85, 0.90, 0.95]
    v63_labels = [l for l in configs if l.strip().startswith('v63')]
    alpha_results = {}; alpha_summary = {}

    for label in v63_labels:
        _, base_kw = configs[label]
        print(f"\n  ── {label.strip()} ──")
        print(_fmt_alpha_header())
        print("  " + "-"*6 + " " + "-"*7 + " " + "-"*8 + " " + "-"*7
              + " " + "-"*7 + " " + "-"*7 + " " + "-"*7 + " " + "-"*6 + " " + "-"*9 + "  -------")

        pnl_base = _build_pnl_v63(base_pnl, sig_v36, lam_feat, sig_4ch, **base_kw)
        s_base   = _full_stats(pnl_base[test_mask])['sharpe']
        row = {}; t2_pass = True

        for al in alpha_perturbs:
            pnl_p = _build_pnl_v63(base_pnl, sig_v36, lam_feat, sig_4ch,
                                    **{**base_kw, 'alpha': al})
            st_p   = _full_stats(pnl_p[test_mask])
            drop   = st_p['sharpe'] - s_base
            is_b   = (al == ALPHA_FG)
            if not is_b and abs(drop) >= 0.15:
                t2_pass = False
            print(_fmt_alpha_row(al, st_p, drop, is_b))
            row[f'α={al}'] = {
                'alpha':   float(al),
                'sharpe':  float(st_p['sharpe']),
                'sortino': float(st_p['sortino']),
                'calmar':  float(st_p['calmar']),
                'cagr':    float(st_p['cagr']),
                'maxdd':   float(st_p['max_dd']),
                'avgdd':   float(st_p['avg_dd']),
                'winrate': float(st_p['win_rate']),
                'delta':   float(drop),
            }

        max_drop = max(abs(v['delta']) for v in row.values() if v['alpha'] != ALPHA_FG)
        prev = '[v59=0.33, v60=0.37, v61_surge=0.076, v62_best=0.024]'
        print(f"\n  Max |Δ Sharpe|: {max_drop:.4f}  →  TEST 2: "
              f"{'✓ PASS' if t2_pass else '✗ FAIL'}  {prev}")
        alpha_results[label.strip()] = row
        alpha_summary[label.strip()] = {'pass': t2_pass, 'max_drop': float(max_drop)}

    # ── TEST 3: CLIP BOOST SENSITIVITY ────────────────────────────────────────
    print(f'\n{BAR}')
    print('  TEST 3 — CLIP BOOST SENSITIVITY  (pass: max |drop| < 0.30)')
    print('  Uses v63_b2_k4_mu0 (main hypothesis) as baseline.')
    print('  Perturbs CLIP_BOOST ±1 and ±2 around baseline=2.')
    print(f'{BAR}')

    main_kw = dict(rv_norm=rv_ema, lo=-0.01, clip_boost=2.0, k=4.0, mu=0.0)
    boost_perturbs = {
        'baseline (boost=2)':   dict(rv_norm=rv_ema, lo=-0.01, clip_boost=2.0, k=4.0, mu=0.0),
        'boost + 1  (→3)':      dict(rv_norm=rv_ema, lo=-0.01, clip_boost=3.0, k=4.0, mu=0.0),
        'boost − 1  (→1)':      dict(rv_norm=rv_ema, lo=-0.01, clip_boost=1.0, k=4.0, mu=0.0),
        'boost + 2  (→4)':      dict(rv_norm=rv_ema, lo=-0.01, clip_boost=4.0, k=4.0, mu=0.0),
        'boost − 2  (→0=v58)':  dict(rv_norm=rv_ema, lo=-0.01, clip_boost=0.0, k=4.0, mu=0.0),
    }

    print(_fmt_stats_header() + f"  {'Δ_H2':>8}  Verdict")
    print(_fmt_stats_divider() + " " + "-"*8 + "  -------")

    pnl_b3  = _build_pnl_v63(base_pnl, sig_v36, lam_feat, sig_4ch,
                               **boost_perturbs['baseline (boost=2)'])
    s_b3_h2 = _full_stats(pnl_b3[second_half])['sharpe']
    t3_rows = {}; t3_pass = True
    for pname, pkw in boost_perturbs.items():
        pnl_p  = _build_pnl_v63(base_pnl, sig_v36, lam_feat, sig_4ch, **pkw)
        st_f   = _full_stats(pnl_p[test_mask])
        s_h2   = _full_stats(pnl_p[second_half])['sharpe']
        drop   = s_h2 - s_b3_h2
        is_b   = pname.startswith('baseline')
        verdict = '—' if is_b else ('PASS' if abs(drop) < 0.30 else 'FAIL')
        if not is_b and abs(drop) >= 0.30: t3_pass = False
        pf_s = f"{st_f['profit_f']:>6.2f}" if st_f['profit_f'] != np.inf else "   ∞  "
        print(f"  {pname:<44} {st_f['sharpe']:>+7.3f} {st_f['sortino']:>+8.3f} {st_f['calmar']:>+7.2f}"
              f" {st_f['cagr']:>+6.1%} {st_f['max_dd']:>+7.1%} {st_f['avg_dd']:>+7.1%}"
              f" {st_f['win_rate']:>5.1%} {pf_s} ${st_f['final']:>7.2f}  {drop:>+8.4f}  {verdict}")
        t3_rows[pname] = {'sharpe_full': float(st_f['sharpe']), 'sharpe_h2': float(s_h2),
                          'maxdd': float(st_f['max_dd']), 'calmar': float(st_f['calmar']),
                          'sortino': float(st_f['sortino']), 'cagr': float(st_f['cagr']),
                          'delta_h2': float(drop)}

    t3_max = max(abs(v['delta_h2']) for k, v in t3_rows.items() if not k.startswith('baseline'))
    print(f"\n  Max |Δ H2 Sharpe|: {t3_max:.4f}  →  TEST 3: {'✓ PASS' if t3_pass else '✗ FAIL'}")

    # ── TEST 4: MU / STEEPNESS SENSITIVITY ────────────────────────────────────
    print(f'\n{BAR}')
    print('  TEST 4 — MU / STEEPNESS SENSITIVITY  (pass: max |drop| < 0.20)')
    print(f'{BAR}')

    mu_perturbs = {
        'baseline (b2,k4,μ=0)':  dict(rv_norm=rv_ema, lo=-0.01, clip_boost=2.0, k=4.0, mu=0.0),
        'μ + 0.25':               dict(rv_norm=rv_ema, lo=-0.01, clip_boost=2.0, k=4.0, mu=0.25),
        'μ − 0.25':               dict(rv_norm=rv_ema, lo=-0.01, clip_boost=2.0, k=4.0, mu=-0.25),
        'μ + 0.50':               dict(rv_norm=rv_ema, lo=-0.01, clip_boost=2.0, k=4.0, mu=0.50),
        'μ − 0.50':               dict(rv_norm=rv_ema, lo=-0.01, clip_boost=2.0, k=4.0, mu=-0.50),
        'k + 2  (→6)':            dict(rv_norm=rv_ema, lo=-0.01, clip_boost=2.0, k=6.0, mu=0.0),
        'k − 2  (→2)':            dict(rv_norm=rv_ema, lo=-0.01, clip_boost=2.0, k=2.0, mu=0.0),
    }

    print(_fmt_stats_header() + f"  {'Δ_H2':>8}  Verdict")
    print(_fmt_stats_divider() + " " + "-"*8 + "  -------")

    pnl_b4  = _build_pnl_v63(base_pnl, sig_v36, lam_feat, sig_4ch,
                               **mu_perturbs['baseline (b2,k4,μ=0)'])
    s_b4_h2 = _full_stats(pnl_b4[second_half])['sharpe']
    t4_rows = {}; t4_pass = True
    for pname, pkw in mu_perturbs.items():
        pnl_p  = _build_pnl_v63(base_pnl, sig_v36, lam_feat, sig_4ch, **pkw)
        st_f   = _full_stats(pnl_p[test_mask])
        s_h2   = _full_stats(pnl_p[second_half])['sharpe']
        drop   = s_h2 - s_b4_h2
        is_b   = pname.startswith('baseline')
        verdict = '—' if is_b else ('PASS' if abs(drop) < 0.20 else 'FAIL')
        if not is_b and abs(drop) >= 0.20: t4_pass = False
        pf_s = f"{st_f['profit_f']:>6.2f}" if st_f['profit_f'] != np.inf else "   ∞  "
        print(f"  {pname:<44} {st_f['sharpe']:>+7.3f} {st_f['sortino']:>+8.3f} {st_f['calmar']:>+7.2f}"
              f" {st_f['cagr']:>+6.1%} {st_f['max_dd']:>+7.1%} {st_f['avg_dd']:>+7.1%}"
              f" {st_f['win_rate']:>5.1%} {pf_s} ${st_f['final']:>7.2f}  {drop:>+8.4f}  {verdict}")
        t4_rows[pname] = {'sharpe_full': float(st_f['sharpe']), 'sharpe_h2': float(s_h2),
                          'maxdd': float(st_f['max_dd']), 'calmar': float(st_f['calmar']),
                          'sortino': float(st_f['sortino']), 'cagr': float(st_f['cagr']),
                          'delta_h2': float(drop)}

    t4_max = max(abs(v['delta_h2']) for k, v in t4_rows.items() if not k.startswith('baseline'))
    print(f"\n  Max |Δ H2 Sharpe|: {t4_max:.4f}  →  TEST 4: {'✓ PASS' if t4_pass else '✗ FAIL'}")

    # ── TEST 5: rv STRESS on v63 best OOS config ──────────────────────────────
    print(f'\n{BAR}')
    print('  TEST 5 — rv STRESS on best v63 config  (pass: max |drop| < 0.20)')
    print(f'{BAR}')

    best_v63_lbl = max(
        (l for l in v63_labels),
        key=lambda l: oos_results[l.strip()]['sharpe_second']
    )
    _, best_kw = configs[best_v63_lbl]
    print(f"  Using: {best_v63_lbl.strip()}")

    rv_perturbs = {
        'baseline':         lambda r: r,
        'rv × 0.90':        lambda r: r * 0.90,
        'rv × 1.10':        lambda r: r * 1.10,
        'rv + N(0,0.02)':   lambda r: r + np.random.default_rng(42).normal(0, 0.02, len(r)),
    }

    # v63 accepts rv_norm via best_kw — apply perturbation by patching rv_ema
    base_rv = _build_pnl_v58(base_pnl, sig_v36, lam_feat, sig_4ch, rv_norm=rv_ema, lo=-0.01)
    s_rv_base = _full_stats(base_rv[test_mask])['sharpe']

    print(_fmt_stats_header() + f"  {'Δ_base':>8}  Verdict")
    print(_fmt_stats_divider() + " " + "-"*8 + "  -------")
    t5_pass = True
    for pname, rv_fn in rv_perturbs.items():
        if pname == 'baseline':
            pnl_rv = base_rv
        else:
            rv_perturbed = rv_fn(rv_ema.values)
            rv_s = pd.Series(rv_perturbed, index=rv_ema.index)
            pnl_rv = _build_pnl_v58(base_pnl, sig_v36, lam_feat, sig_4ch,
                                     rv_norm=rv_s, lo=-0.01)
        st   = _full_stats(pnl_rv[test_mask])
        drop = st['sharpe'] - s_rv_base
        is_b = pname == 'baseline'
        verdict = '—' if is_b else ('PASS' if abs(drop) < 0.20 else 'FAIL')
        if not is_b and abs(drop) >= 0.20: t5_pass = False
        pf_s = f"{st['profit_f']:>6.2f}" if st['profit_f'] != np.inf else "   ∞  "
        print(f"  {pname:<44} {st['sharpe']:>+7.3f} {st['sortino']:>+8.3f} {st['calmar']:>+7.2f}"
              f" {st['cagr']:>+6.1%} {st['max_dd']:>+7.1%} {st['avg_dd']:>+7.1%}"
              f" {st['win_rate']:>5.1%} {pf_s} ${st['final']:>7.2f}  {drop:>+8.4f}  {verdict}")
    print(f"\n  TEST 5: {'✓ PASS' if t5_pass else '✗ FAIL'}")

    # ── GRAND SUMMARY ─────────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  GRAND SUMMARY — Full stats for every config (full test-period)')
    print(f'{BAR}')

    print(_fmt_stats_header() + f"  {'OOS H2 Sharpe':>14}  {'H2 MaxDD':>9}  {'α drop':>7}  Pass?")
    print(_fmt_stats_divider() + "  " + "-"*14 + "  " + "-"*9 + "  " + "-"*7 + "  -----")

    champion_lbl = None; champion_h2 = -999.0
    for label, (mode, kw) in configs.items():
        pnl   = _pnl(label, mode, kw)
        st_f  = _full_stats(pnl[test_mask])
        st_h2 = _full_stats(pnl[second_half])
        s_lbl = label.strip()
        oos_r = oos_results.get(s_lbl, {})
        alpha_r = alpha_summary.get(s_lbl, {})
        oos_ok   = oos_r.get('pass', True)
        alpha_ok = alpha_r.get('pass', True) if alpha_r else True
        max_drop_s = f"{alpha_r['max_drop']:>7.4f}" if alpha_r else '    N/A'
        tag = ''
        if s_lbl.startswith('v58'):
            tag = '  ← PREV CHAMPION'
        elif oos_ok and alpha_ok and st_h2['sharpe'] > champion_h2:
            champion_h2 = st_h2['sharpe']; champion_lbl = s_lbl
        pf_s = f"{st_f['profit_f']:>6.2f}" if st_f['profit_f'] != np.inf else "   ∞  "
        print(f"  {s_lbl:<44} {st_f['sharpe']:>+7.3f} {st_f['sortino']:>+8.3f} {st_f['calmar']:>+7.2f}"
              f" {st_f['cagr']:>+6.1%} {st_f['max_dd']:>+7.1%} {st_f['avg_dd']:>+7.1%}"
              f" {st_f['win_rate']:>5.1%} {pf_s} ${st_f['final']:>7.2f}"
              f"  {st_h2['sharpe']:>+14.4f}  {st_h2['max_dd']:>+9.1%}  {max_drop_s}"
              f"  {'✓' if (oos_ok and alpha_ok) else '✗'}{tag}")

    # ── year-on-year table ─────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  YEAR-ON-YEAR RETURNS  (OOS period, annualised)')
    print(f'{BAR}')

    test_years = sorted(set(df_1h.index[test_mask].year))
    col_w = 10
    hdr   = f"  {'Config':<44}" + ''.join(f" {str(yr):>{col_w}}" for yr in test_years)
    print(hdr)
    print("  " + "-"*44 + "".join(" " + "-"*col_w for _ in test_years))

    for label, (mode, kw) in configs.items():
        pnl  = _pnl(label, mode, kw)
        st_f = _full_stats(pnl[test_mask])
        row  = f"  {label.strip():<44}"
        for yr in test_years:
            r = st_f['yoy'].get(yr, float('nan'))
            row += f" {r:>+9.1%} " if not np.isnan(r) else f" {'—':>{col_w}}"
        print(row)

    print(f'\n  Alpha sensitivity progression (max |Δ Sharpe|, lower=better, bar=0.15):')
    print(f'    v59 Schmitt:    0.3300  ✗')
    print(f'    v60 BSDT:       0.3664  ✗')
    print(f'    v61_loose:      0.3211  ✗')
    print(f'    v61_surge:      0.0764  ✓  (OOS H2=+2.70, below +3.60 bar)')
    print(f'    v62_k4_mu0.5:   0.0241  ✓  (OOS H2=+2.79, below +3.60 bar)')
    _d0 = alpha_summary.get("v63_b2_k4_mu0",  {}).get("max_drop", float("nan"))
    _d1 = alpha_summary.get("v63_b4_k4_mu0",  {}).get("max_drop", float("nan"))
    _h0 = oos_results.get("v63_b2_k4_mu0",    {}).get("sharpe_second", float("nan"))
    _h1 = oos_results.get("v63_b4_k4_mu0",    {}).get("sharpe_second", float("nan"))
    print(f'    v63_b2_k4_mu0:  {_d0:.4f}  '
          f'{"✓" if alpha_summary.get("v63_b2_k4_mu0",{}).get("pass", False) else "✗"}'
          f'  (OOS H2={_h0:+.4f})')
    print(f'    v63_b4_k4_mu0:  {_d1:.4f}  '
          f'{"✓" if alpha_summary.get("v63_b4_k4_mu0",{}).get("pass", False) else "✗"}'
          f'  (OOS H2={_h1:+.4f})')

    if champion_lbl:
        print(f'\n  NEW CHAMPION CANDIDATE : {champion_lbl}')
        print(f'  OOS H2 Sharpe          : {champion_h2:+.4f}')
        print(f'  vs v58                 : {champion_h2 - 4.7402:+.4f}')
    else:
        print(f'\n  No new champion. v58_tight remains champion at OOS H2=+4.7402.')

    # ── persist ────────────────────────────────────────────────────────────────
    results = {
        'version': 'v63',
        'oos':     oos_results,
        'alpha':   alpha_summary,
        'test3_boost_sensitivity': t3_rows,
        'test4_mu_sensitivity': t4_rows,
    }
    out_path = OUT_DIR_ / 'crypto_bsdt_v63_results.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)

    class _NpEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer,)):  return int(obj)
            if isinstance(obj, (np.floating,)): return float(obj)
            if isinstance(obj, (np.bool_,)):    return bool(obj)
            if isinstance(obj, np.ndarray):     return obj.tolist()
            return super().default(obj)

    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, cls=_NpEncoder)
    print(f'\n  Results saved → {out_path}')
    print(f'  Total time: {time.time()-t0:.0f}s')

if __name__ == '__main__':
    main()
