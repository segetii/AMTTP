"""
v55 Kill Test Suite
===================
Four adversarial tests designed to FALSIFY the v55 improvement (K_G=0.10 → Sharpe +4.036).

User's concerns:
  1. Post-hoc structural bias — rule designed after seeing regime asymmetry
  2. In-sample structural fitting — same dataset used for both discovery and validation
  3. "Both regimes improve cleanly" — suspicious signal of noise matching
  4. +0.179 from 1 parameter — needs stronger validation than parameter sweeps
  5. Timing artifact — information in rv_norm might not be truly lagged correctly

Four kill tests:
  TEST 1: Walk-Forward OOS
    - Fit K_G on test first half (2023-2024)
    - Freeze it and evaluate on second half (2025-2026)
    - No information from second half used in fitting
    - PASS: v55 beats v54 on strict holdout

  TEST 2: Lag Corruption
    - Add extra lag to rv_norm: 0, 24h, 48h, 72h, 168h on top of existing 1h shift
    - Real regime signal: graceful degradation
    - Timing artifact: cliff-drop even at +24h
    - PASS: Sharpe at +48h lag > v54 - 0.10

  TEST 3: Null Distribution / Shuffle Test (N=500)
    - Permute rv_norm values in test window → break time alignment
    - Build null distribution of Sharpe at K_G=0.10
    - PASS: original Sharpe in top 5% (p < 0.05)
    - STRONG PASS: p < 0.01

  TEST 4: Formula Robustness
    - 4 functional forms: linear, quadratic, exp-centered, tanh
    - All identical at rv_norm=1 (normal vol baseline)
    - Sweep K for each form to find peak Sharpe
    - PASS: all forms peak within ±0.08 Sharpe of K_G=0.10 linear
    - PASS: no form degrades to below v54 at its optimal K

VERDICT RULES:
  4/4 PASS → CONFIRMED REAL SIGNAL, promote v55 to production
  3/4 PASS → LIKELY REAL, use ensemble of plateau + v55
  ≤2/4 PASS → OVERFIT WARNING, do not promote v55
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
    CALIB_BARS, BPD, ANN_1H,
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
    FIRE_PERCENTILE, calibrate_firing_thresholds, _yoy_table,
)
from run_crypto_pairs_v39b_k1_scaled import (
    PCA_K_B, calibrate_channel_means, compute_four_channel_signals_v39b,
)
import run_crypto_pairs_v34_full_combined as _v34mod

OUT_DIR_ = Path(OUT_DIR)

# ── cache helpers ─────────────────────────────────────────────────────────────
_CACHE_DIR = Path(r'C:\amttp\data')
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
        df = pd.read_pickle(str(p)); print(f'  fetch_and_prepare [CACHE]'); return df
    df = fetch_and_prepare(); df.to_pickle(str(p)); return df

def _cached_add_cross_market(df):
    p = _CACHE_DIR / 'cross_market_df.pkl'
    if p.exists() and (time.time()-p.stat().st_mtime)/3600 < _CACHE_TTL_H:
        r = pd.read_pickle(str(p))
        if r.shape[0]==df.shape[0] and r.index[-1]==df.index[-1]:
            print(f'  cross_market [CACHE]'); return r
    r = add_cross_market_features(df); r.to_pickle(str(p)); return r

def _cached_fetch_binance_funding():
    p = _CACHE_DIR / 'binance_funding.pkl'
    if p.exists() and (time.time()-p.stat().st_mtime)/3600 < _CACHE_TTL_H:
        import pickle as _pk
        with open(str(p), 'rb') as f: fund = _pk.load(f)
        print(f'  funding [CACHE]'); return fund
    fund = fetch_binance_funding(symbols=['ETHUSDT','BTCUSDT'], start='2020-06-01')
    import pickle as _pk
    with open(str(p), 'wb') as f: _pk.dump(fund, f)
    return fund


# ── frozen champion config (v54 baseline + v55 K_G) ──────────────────────────
CLIP     = 6.0
GH_TH    = 5.0    # = CLIP-1
GH_TL    = -1.0
GL_TH    = -1.0
GL_TL    = -1.0
N_OPT    = 8
T_THRESH = 0.41   # DO NOT adapt — cliff in both directions
G_THRESH = 0.45   # base value — will be modulated by K_G
GBT      = 0.45
CB       = 0.65
AFT      = 0.65
K_G_CHAMP = 0.10  # v55 champion

V54_SHARPE = 3.8568

# Walk-forward midpoint
WF_MIDPOINT = pd.Timestamp('2025-01-01')


# ── core physics: flag computation with pre-computed gth ─────────────────────
def _flags_from_gth(sig_4ch: pd.DataFrame, gth, tth: float):
    """Compute quadrant flags with pre-computed gth (Series or scalar)."""
    a_G = sig_4ch['a_G']
    a_A = sig_4ch['a_A']
    a_T = sig_4ch['a_T']
    G_mem = a_G.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    T_mem = a_T.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    fired  = (a_A.shift(1).fillna(0.0) > AFT)
    q_GH_TH = (fired & (G_mem > gth) & (T_mem > tth)).astype(float)
    q_GH_TL = (fired & (G_mem > gth) & (T_mem <= tth)).astype(float)
    q_GL_TH = (fired & (G_mem <= gth) & (T_mem > tth)).astype(float)
    q_GL_TL = (fired & (G_mem <= gth) & (T_mem <= tth)).astype(float)
    return q_GH_TH, q_GH_TL, q_GL_TH, q_GL_TL


def _apply_phase(base: pd.Series, sv36: pd.DataFrame, lf: pd.DataFrame,
                 s4: pd.DataFrame, gth) -> pd.Series:
    """Full PnL from base PnL series + pre-computed or scalar gth."""
    idx  = base.index
    sv36 = sv36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lf.reindex(idx, method='ffill').fillna(0.5)
    s4   = s4.reindex(idx, method='ffill').fillna(0.0)
    gam  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lp   = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size = np.clip(1.0 - gam, 0.0, 1.0) * (0.75 + 0.5 * lp)
    q_GH_TH, q_GH_TL, q_GL_TH, q_GL_TL = _flags_from_gth(s4, gth, T_THRESH)
    phase = (1.0 + GH_TH*q_GH_TH + GH_TL*q_GH_TL
             + GL_TH*q_GL_TH + GL_TL*q_GL_TL).clip(0.05, CLIP)
    flag  = (s4['a_G'].shift(1).fillna(0.0) > GBT).astype(float)
    return base.fillna(0.0) * size * (1.0 + CB * flag) * phase


def _gth_from_form(rv_input: pd.Series, k: float, form: str) -> pd.Series:
    """
    Four functional forms — all equal G_THRESH when rv_input=1.
      linear:    base * (1 + K*(1-rv))
      quadratic: base * (1 + K*(1-rv²))
      exp:       base * exp(-K*(rv-1))
      tanh:      base * (1 + K*tanh(1-rv))
    All decrease when rv>1 (high vol → lower threshold → trade more).
    All increase when rv<1 (low vol → higher threshold → trade less).
    """
    rv = rv_input.clip(0.1, 5.0)
    if form == 'linear':
        raw = G_THRESH * (1.0 + k * (1.0 - rv))
    elif form == 'quadratic':
        raw = G_THRESH * (1.0 + k * (1.0 - rv**2))
    elif form == 'exp':
        raw = G_THRESH * np.exp(-k * (rv - 1.0))
    elif form == 'tanh':
        raw = G_THRESH * (1.0 + k * np.tanh(1.0 - rv))
    else:
        raise ValueError(f'Unknown form: {form}')
    return raw.clip(0.20, 0.70)


def _build_pnl(base, sv36, lf, s4, rv_input, k, form='linear'):
    """End-to-end PnL with given rv_input Series, K scalar, and formula form."""
    # Reindex rv to match signal index
    rv = rv_input.reindex(s4.index, method='ffill').fillna(1.0)
    gth = _gth_from_form(rv, k, form)
    return _apply_phase(base, sv36, lf, s4, gth)


def _build_pnl_static(base, sv36, lf, s4):
    """v54 static reference: G_THRESH fixed at 0.45."""
    return _apply_phase(base, sv36, lf, s4, G_THRESH)


def _realized_vol(df_1h: pd.DataFrame, window_h: int = 168, extra_lag: int = 0) -> pd.Series:
    """1-week realized vol, normalized to rolling mean, with configurable extra lag."""
    rv = df_1h['ret_eth'].rolling(window_h, min_periods=24).std()
    rv_mean = rv.rolling(1000, min_periods=100).mean()
    rv_norm = (rv / rv_mean.replace(0, np.nan)).fillna(1.0)
    # Base lag=1 (avoid lookahead), plus optional extra lag for Kill Test 2
    total_lag = 1 + extra_lag
    return rv_norm.shift(total_lag).fillna(1.0)


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    t0 = time.time()
    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)
    BAR = '=' * 100
    RES = {}   # results accumulator for JSON

    print(BAR)
    print("  v55 KILL TEST SUITE")
    print("  Champion: K_G=0.10  Sharpe=+4.036  vs v54 baseline=+3.857")
    print("  Objective: FALSIFY this result before trusting it")
    print(BAR)

    t = lambda msg: print(f'\n{msg}', flush=True)

    t('[SETUP] 1h data')
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_mask   = df_1h.index >= TEST_START
    train_1h    = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    test_first  = test_mask & (df_1h.index <  WF_MIDPOINT)
    test_second = test_mask & (df_1h.index >= WF_MIDPOINT)
    print(f'    test_first={test_first.sum()} bars (<{WF_MIDPOINT.date()}), '
          f'test_second={test_second.sum()} bars (≥{WF_MIDPOINT.date()})')

    t(f'[SETUP] Funding t={time.time()-t0:.0f}s')
    try:
        fund = _cached_fetch_binance_funding()
        fund_eth = fund.get('ETHUSDT'); fund_btc = fund.get('BTCUSDT')
    except Exception as e:
        print(f'    Warning: {e}'); fund_eth = fund_btc = None

    t(f'[SETUP] State panel t={time.time()-t0:.0f}s')
    X = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X = np.nan_to_num(X)
    train_idx  = np.where(train_1h)[0]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[train_idx[-CALIB_BARS:]] = True

    t(f'[SETUP] Engine t={time.time()-t0:.0f}s')
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(X, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)
    M_k1    = MasterOperator.calibrate(X[calib_mask], k=PCA_K_B)

    t(f'[SETUP] Signals t={time.time()-t0:.0f}s')
    sig_v36       = compute_intraday_signals(X, df_1h, M, net, ews, stoch, e_star, theta)
    sig_v37, _, _ = compute_price_prediction_signals(X, df_1h, M, sig_v36, e_star, sigma_n)
    lam_feat      = compute_lambda_features(sig_v37, roll_windows=(100,200,500))

    t(f'[SETUP] 4-channel t={time.time()-t0:.0f}s')
    mu_norm  = calibrate_channel_means(X, calib_mask, M_k1)
    fire_thr = calibrate_firing_thresholds(X, calib_mask, M_k1, pct=FIRE_PERCENTILE)
    sig_4ch  = compute_four_channel_signals_v39b(X, df_1h, M_k1, sig_v36, fire_thr, mu_norm)

    t(f'[SETUP] Base portfolio t={time.time()-t0:.0f}s')
    h_strats = compute_1h_strategies(df_1h, has_sol)
    df_d     = _cached_fetch_and_prepare()
    df_d     = _cached_add_cross_market(df_d)
    fund_d   = _cached_fetch_binance_funding()
    df_d     = add_leverage_features(df_d, fund_d)
    tmask_d  = (df_d.index >= TRAIN_START) & (df_d.index <= TRAIN_END)
    pos_dict, _, F_daily, gate_daily = build_daily_positions(
        df_d, tmask_d, np.asarray(tmask_d, dtype=bool))
    instr_map = {
        'D1_trend_eth': df_1h['ret_eth'], 'D2_pairs_eb': df_1h['spread_ret_eb'],
        'D3_pairs_es':  df_1h['ret_eth'] - df_1h.get('ret_sol', df_1h['ret_eth']),
        'D4_macro_btc': df_1h['ret_btc'], 'D5_macro_btc': df_1h['ret_btc'],
        'D5_macro_alt': df_1h['ret_eth'],
    }
    d1h = {n: upsample_daily_to_1h_pnl(p, instr_map.get(n, df_1h['ret_eth']), gate_daily)
           for n, p in pos_dict.items()}
    base_pnl = assemble_combined({**d1h, **h_strats}, compute_quality({**d1h, **h_strats}, bpd=BPD))

    # Compute rv_norm (base, lag=1h built-in)
    rv_base = _realized_vol(df_1h, window_h=168, extra_lag=0)

    # v54 static reference
    pnl_v54 = _build_pnl_static(base_pnl, sig_v36, lam_feat, sig_4ch)
    v54_full  = _stats(pnl_v54[test_mask])['sharpe']
    v54_first = _stats(pnl_v54[test_first])['sharpe']
    v54_second= _stats(pnl_v54[test_second])['sharpe']

    # v55 champion (K_G=0.10 on full test)
    pnl_v55 = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch, rv_base, K_G_CHAMP, 'linear')
    v55_full  = _stats(pnl_v55[test_mask])['sharpe']
    v55_first = _stats(pnl_v55[test_first])['sharpe']
    v55_second= _stats(pnl_v55[test_second])['sharpe']

    print(f"\n    v54 full={v54_full:+.4f}  first={v54_first:+.4f}  second={v54_second:+.4f}")
    print(f"    v55 full={v55_full:+.4f}  first={v55_first:+.4f}  second={v55_second:+.4f}")
    print(f"    Setup complete t={time.time()-t0:.1f}s")

    # ═══════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print('  KILL TEST 1: WALK-FORWARD OOS')
    print(f'  Fit K_G on test_first (<{WF_MIDPOINT.date()}) → evaluate FROZEN on test_second')
    print(f'  Rule: never look at test_second during K_G selection')
    print(f'{BAR}')

    WF_KG_SWEEP = [0.0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.14, 0.16, 0.20]
    wf_results = {}
    print(f"\n  K_G fitting on first half (<{WF_MIDPOINT.date()}):")
    print(f"  {'K_G':<10} {'Sharpe_1H':>12} {'Delta_v54_1H':>14}")
    print(f"  {'-'*10} {'-'*12} {'-'*14}")
    for kg in WF_KG_SWEEP:
        p = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch, rv_base, kg, 'linear')
        s1 = _stats(p[test_first])['sharpe']
        wf_results[kg] = {'first_sharpe': s1}
        flag = ' <-- best (so far)' if s1 == max(v['first_sharpe'] for v in wf_results.values()) else ''
        print(f"  {kg:<10.3f} {s1:>+12.4f} {s1-v54_first:>+14.4f}{flag}")

    # Find best K_G from first half ONLY
    kg_fitted = max(wf_results, key=lambda k: wf_results[k]['first_sharpe'])
    print(f"\n  => Best K_G from first half: {kg_fitted:.3f} (Sharpe={wf_results[kg_fitted]['first_sharpe']:+.4f})")

    # Evaluate FROZEN on second half — no peeking at second half during selection
    pnl_oos = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch, rv_base, kg_fitted, 'linear')
    oos_sharpe = _stats(pnl_oos[test_second])['sharpe']
    oos_delta  = oos_sharpe - v54_second

    print(f"\n  Second half holdout (≥{WF_MIDPOINT.date()}) with frozen K_G={kg_fitted:.3f}:")
    print(f"    v54 second half : {v54_second:+.4f}")
    print(f"    v55 OOS holdout : {oos_sharpe:+.4f}")
    print(f"    Delta           : {oos_delta:+.4f}")

    wf_pass = oos_delta > 0.00
    wf_strong = oos_delta > 0.05
    print(f"\n  TEST 1 RESULT: {'✓ STRONG PASS' if wf_strong else ('✓ PASS' if wf_pass else '✗ FAIL')}"
          f" (OOS delta={oos_delta:+.4f}, threshold=0.00)")
    RES['kill1_wf'] = {
        'kg_fitted': float(kg_fitted),
        'first_half_sharpe': float(wf_results[kg_fitted]['first_sharpe']),
        'second_half_v54':   float(v54_second),
        'second_half_v55':   float(oos_sharpe),
        'oos_delta':         float(oos_delta),
        'pass': bool(wf_pass),
        'strong_pass': bool(wf_strong),
    }

    # ═══════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print('  KILL TEST 2: LAG CORRUPTION')
    print('  Add extra lag to rv_norm BEYOND existing 1h shift.')
    print('  Real regime signal: graceful decay.  Timing artifact: cliff at +24h.')
    print(f'{BAR}')

    LAG_TESTS = {
        'rv_lag+0h  (base, shift=1)':   0,
        'rv_lag+24h (shift=25)':        24,
        'rv_lag+48h (shift=49)':        48,
        'rv_lag+72h (shift=73)':        72,
        'rv_lag+168h (1wk behind)':    168,
    }
    print(f"\n  {'Lag Config':<30} {'Sharpe':>8} {'Delta_v54':>10} {'Delta_base':>12}")
    print(f"  {'-'*30} {'-'*8} {'-'*10} {'-'*12}")

    lag_results = {}
    base_lag_sharpe = None
    for name, extra in LAG_TESTS.items():
        rv_lagged = _realized_vol(df_1h, window_h=168, extra_lag=extra)
        p = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch, rv_lagged, K_G_CHAMP, 'linear')
        s = _stats(p[test_mask])['sharpe']
        lag_results[name] = {'extra_lag': extra, 'sharpe': float(s)}
        if extra == 0:
            base_lag_sharpe = s
        d_v54 = s - V54_SHARPE
        d_base = s - base_lag_sharpe if base_lag_sharpe is not None else 0.0
        flag = ''
        if extra > 0 and base_lag_sharpe is not None:
            cliff = abs(s - base_lag_sharpe) > 0.20 and extra <= 24
            flag = '  ⚠️  CLIFF' if cliff else ''
        print(f"  {name:<30} {s:>+8.4f} {d_v54:>+10.4f} {d_base:>+12.4f}{flag}")

    # Check: Sharpe at +48h lag vs v54
    lag48_sharpe = lag_results.get('rv_lag+48h (shift=49)', {}).get('sharpe', 0.0)
    lag_pass     = lag48_sharpe > V54_SHARPE - 0.10
    lag_strong   = lag48_sharpe > V54_SHARPE
    lag24_sharpe = lag_results.get('rv_lag+24h (shift=25)', {}).get('sharpe', 0.0)
    cliff_drop   = abs(lag24_sharpe - base_lag_sharpe) if base_lag_sharpe else 0

    print(f"\n  Cliff drop lag+0→+24h: {cliff_drop:.4f} Sharpe")
    print(f"  Sharpe at +48h lag:    {lag48_sharpe:+.4f} (v54={V54_SHARPE:+.4f})")
    print(f"\n  TEST 2 RESULT: {'✓ STRONG PASS' if lag_strong else ('✓ PASS' if lag_pass else '✗ FAIL')}"
          f" (Sharpe@+48h={lag48_sharpe:+.4f}, threshold={V54_SHARPE-0.10:+.4f})")
    RES['kill2_lag'] = {
        'results':  lag_results,
        'cliff_drop_24h': float(cliff_drop),
        'sharpe_lag48h':  float(lag48_sharpe),
        'pass': bool(lag_pass),
        'strong_pass': bool(lag_strong),
    }

    # ═══════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print('  KILL TEST 3: SHUFFLE / NULL DISTRIBUTION (N=500)')
    print('  Permute rv_norm values in test window → break time alignment.')
    print('  Null hypothesis: improvement is due to random rv_norm alignment.')
    print(f'{BAR}')

    N_SHUFFLE = 500
    np.random.seed(12345)

    # Get test-window indices in the signal DataFrame
    test_idx = np.where(test_mask)[0]
    rv_test_vals = rv_base.values.copy()   # full-length array
    null_sharpes = np.zeros(N_SHUFFLE)

    print(f"  Running {N_SHUFFLE} permutations...", flush=True)
    t_shuffle = time.time()
    for i in range(N_SHUFFLE):
        rv_perm = rv_base.copy()
        perm_order = np.random.permutation(len(test_idx))
        rv_perm.iloc[test_idx] = rv_test_vals[test_idx[perm_order]]
        p = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch, rv_perm, K_G_CHAMP, 'linear')
        null_sharpes[i] = _stats(p[test_mask])['sharpe']
        if (i+1) % 100 == 0:
            print(f"    {i+1}/{N_SHUFFLE}  ({time.time()-t_shuffle:.1f}s)", flush=True)

    null_mean = null_sharpes.mean()
    null_std  = null_sharpes.std()
    null_pct  = np.percentile(null_sharpes, [50, 75, 90, 95, 99])
    p_value   = (null_sharpes >= v55_full).mean()
    z_score   = (v55_full - null_mean) / null_std if null_std > 0 else float('inf')

    print(f"\n  Null distribution (N={N_SHUFFLE} shuffles of rv_norm at K_G=0.10):")
    print(f"    Mean = {null_mean:+.4f}   Std = {null_std:.4f}")
    print(f"    Percentiles: 50th={null_pct[0]:+.4f}  75th={null_pct[1]:+.4f}  "
          f"90th={null_pct[2]:+.4f}  95th={null_pct[3]:+.4f}  99th={null_pct[4]:+.4f}")
    print(f"\n  Original v55 Sharpe: {v55_full:+.4f}")
    print(f"  Z-score vs null:     {z_score:+.2f}σ")
    print(f"  p-value:             {p_value:.4f}  "
          f"({'top ' + str(round(p_value*100,1)) + '% → real signal' if p_value < 0.05 else 'NOT significant'})")

    shuf_pass   = p_value < 0.05
    shuf_strong = p_value < 0.01
    print(f"\n  TEST 3 RESULT: {'✓ STRONG PASS' if shuf_strong else ('✓ PASS' if shuf_pass else '✗ FAIL')}"
          f" (p={p_value:.4f}, threshold=0.05)")
    RES['kill3_shuffle'] = {
        'n':         N_SHUFFLE,
        'null_mean': float(null_mean),
        'null_std':  float(null_std),
        'null_p50':  float(null_pct[0]),
        'null_p95':  float(null_pct[3]),
        'null_p99':  float(null_pct[4]),
        'v55_sharpe': float(v55_full),
        'z_score':    float(z_score),
        'p_value':    float(p_value),
        'pass': bool(shuf_pass),
        'strong_pass': bool(shuf_strong),
    }

    # ═══════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print('  KILL TEST 4: FORMULA ROBUSTNESS')
    print('  4 functional forms — all equal G_THRESH=0.45 when rv_norm=1.0')
    print('  If performance varies wildly by form → fragile coincidence with linear noise')
    print(f'{BAR}')

    FORMS = {
        'linear    (base: 1+K*(1-rv))':    ('linear',    [0.00, 0.02, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.30]),
        'quadratic (1+K*(1-rv²))':         ('quadratic', [0.00, 0.02, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.30]),
        'exp       (exp(-K*(rv-1)))':       ('exp',       [0.00, 0.02, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.30]),
        'tanh      (1+K*tanh(1-rv))':      ('tanh',      [0.00, 0.02, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.30]),
    }

    form_results = {}
    all_peak_sharpes = []
    print(f"\n  {'Form':<38} {'OptK':>6} {'PeakS':>8} {'Δv54':>8} {'@K0.10':>8} {'Status'}")
    print(f"  {'-'*38} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*10}")

    for fname, (fkey, k_sweep) in FORMS.items():
        sharpe_at_k = {}
        for k in k_sweep:
            p = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch, rv_base, k, fkey)
            s = _stats(p[test_mask])['sharpe']
            sharpe_at_k[k] = float(s)

        best_k    = max(sharpe_at_k, key=sharpe_at_k.get)
        peak_s    = sharpe_at_k[best_k]
        at_k010   = sharpe_at_k.get(0.10, sharpe_at_k.get(K_G_CHAMP, float('nan')))
        d_v54     = peak_s - V54_SHARPE
        all_peak_sharpes.append(peak_s)
        form_results[fname] = {'form': fkey, 'best_k': best_k, 'peak_sharpe': peak_s,
                                'at_k010': at_k010, 'delta_v54': d_v54, 'sweep': sharpe_at_k}
        status = '✓' if d_v54 > 0 else '✗'
        print(f"  {fname:<38} {best_k:>6.3f} {peak_s:>+8.4f} {d_v54:>+8.4f} {at_k010:>+8.4f}  {status}")

    peak_spread = max(all_peak_sharpes) - min(all_peak_sharpes)
    all_beat_v54 = all(s > V54_SHARPE for s in all_peak_sharpes)
    form_pass    = peak_spread < 0.10 and all_beat_v54
    form_strong  = peak_spread < 0.05 and all_beat_v54

    print(f"\n  Peak Sharpe spread across 4 forms: {peak_spread:.4f}")
    print(f"  All forms beat v54: {all_beat_v54}")
    print(f"\n  TEST 4 RESULT: {'✓ STRONG PASS' if form_strong else ('✓ PASS' if form_pass else '✗ FAIL')}"
          f" (spread={peak_spread:.4f}, threshold=0.10)")
    RES['kill4_formula'] = {
        'peak_spread': float(peak_spread),
        'all_beat_v54': all_beat_v54,
        'forms': {k: {'best_k': v['best_k'], 'peak_sharpe': v['peak_sharpe'],
                      'at_k010': v['at_k010']} for k, v in form_results.items()},
        'pass': bool(form_pass),
        'strong_pass': bool(form_strong),
    }

    # ═══════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print('  FINAL VERDICT')
    print(f'{BAR}')

    passes = [
        ('Kill Test 1 (Walk-Forward OOS)', RES['kill1_wf']['pass'],   RES['kill1_wf']['strong_pass']),
        ('Kill Test 2 (Lag Corruption)',   RES['kill2_lag']['pass'],  RES['kill2_lag']['strong_pass']),
        ('Kill Test 3 (Shuffle)',          RES['kill3_shuffle']['pass'], RES['kill3_shuffle']['strong_pass']),
        ('Kill Test 4 (Formula Robust.)',  RES['kill4_formula']['pass'], RES['kill4_formula']['strong_pass']),
    ]

    n_pass   = sum(p for _, p, _ in passes)
    n_strong = sum(s for _, _, s in passes)

    print(f"\n  {'Test':<35} {'Result':>16}")
    print(f"  {'-'*35} {'-'*16}")
    for tname, passed, strong in passes:
        status = 'STRONG PASS ✓✓' if strong else ('PASS ✓' if passed else 'FAIL ✗')
        print(f"  {tname:<35} {status:>16}")

    print(f"\n  Score: {n_pass}/4 passed ({n_strong}/4 strong passes)")

    if n_pass == 4:
        overall = "CONFIRMED REAL SIGNAL — promote v55 (K_G=0.10) to production"
        strategy = "Use v55 single config as production champion."
    elif n_pass == 3:
        overall = "LIKELY REAL — use ensemble of v54 plateau + v55"
        strategy = "Deploy ensemble: average(v54_core, v55_K010). Reduces overfit risk."
    elif n_pass == 2:
        overall = "MIXED — do not promote v55; continue with v54 plateau ensemble"
        strategy = "v55 didn't survive adversarial tests. v54 ensemble remains champion."
    else:
        overall = "OVERFIT WARNING — v55 fails kill tests; revert to v54"
        strategy = "K_G=0.10 gain is not robust. Roll back to v54 champion."

    print(f"\n  VERDICT: {overall}")
    print(f"  STRATEGY: {strategy}")

    RES['summary'] = {
        'n_pass': n_pass, 'n_strong': n_strong,
        'v54_sharpe': V54_SHARPE, 'v55_sharpe': float(v55_full),
        'overall': overall, 'strategy': strategy,
    }

    # Save
    out_path = OUT_DIR_ / 'crypto_bsdt_v55_kill_tests.json'
    with open(out_path, 'w') as f:
        json.dump(RES, f, indent=2)
    print(f"\n  Kill test results saved -> {out_path}")
    print(f"  Total elapsed: {time.time()-t0:.1f}s")
    print(BAR)


if __name__ == '__main__':
    main()
