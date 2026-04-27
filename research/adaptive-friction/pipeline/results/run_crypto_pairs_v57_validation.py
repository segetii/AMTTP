"""
Crypto BSDT — v57: Minimum Viable Robustness Validation
========================================================
Purpose: confirm v55 is real and deployable. Three tests only.

TEST 1 — OOS SPLIT (non-negotiable)
  Full test window 2023-2026 already seen during kill/form-id sweeps.
  Further split into: first_half = 2023-2024,  second_half = 2025-2026.
  K=0.10 is frozen (identified before any second-half data was used).
  Pass: Sharpe_second_half ≥ 3.6

TEST 2 — VOLATILITY INPUT STRESS
  Perturb rv_norm before it reaches the threshold formula:
    rv × 0.9   (systematically lower vol)
    rv × 1.1   (systematically higher vol)
    rv + N(0, 0.02) noise
  Pass: max absolute Sharpe drop vs baseline < 0.15

TEST 3 — COHERENT T_THRESH COUPLING
  Link T_THRESH lightly to the same regime signal:
    tth = 0.41 + 0.01 * (gth_dyn / G_THRESH_BASE - 1)
  One run only. Pass: Sharpe improves → real upgrade path exists.
  Fail: keep current (this is a discovery experiment, not an optimisation).

Champion baseline: clip=6.0, tth=0.41, aft=0.65, cb=0.65, gbt=0.45
  v54: K_G=0.00 → Sharpe +3.857
  v55: K_G=0.10 → Sharpe +4.036
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

# ── v55 champion config (frozen) ─────────────────────────────────────────────
CLIP           = 6.0
GH_TH          = 5.0   # = CLIP - 1  (at-boundary structure)
GH_TL = GL_TH = GL_TL = -1.0
N_OPT          = 8
T_THRESH_BASE  = 0.41  # cliff — static unless §test3 override
G_THRESH_BASE  = 0.45
G_BOOST_THRESH = 0.45
CHAMPION_BOOST = 0.65
A_FIRE_THRESH  = 0.65

V54_SHARPE = 3.8568
V55_SHARPE = 4.0362

# ── date anchors ──────────────────────────────────────────────────────────────
# Full test window: 2023-01-01 to present
# OOS split: first_half = 2023-01-01 to 2024-12-31, second_half = 2025-01-01+
OOS_SPLIT = '2025-01-01'   # boundary between "seen during K identification" and "true holdout"


# ── rv_norm helper ────────────────────────────────────────────────────────────
def _realized_vol(df_1h: pd.DataFrame, window_h: int = 168) -> pd.Series:
    rv      = df_1h['ret_eth'].rolling(window_h, min_periods=24).std()
    rv_mean = rv.rolling(1000, min_periods=100).mean()
    rv_norm = (rv / rv_mean.replace(0, np.nan)).fillna(1.0)
    return rv_norm.shift(1).fillna(1.0)

def _dynamic_gth(rv_norm: pd.Series, k_g: float) -> pd.Series | float:
    if k_g == 0.0:
        return G_THRESH_BASE
    dyn = G_THRESH_BASE * (1.0 + k_g * (1.0 - rv_norm))
    return dyn.clip(0.20, 0.70)


# ── quadrant flags (generalised: accepts optional dynamic T_THRESH) ───────────
def _make_quadrant_flags(
    sig_4ch:   pd.DataFrame,
    rv_norm:   pd.Series,
    k_g:       float,
    tth_dyn:   pd.Series | None = None,   # if None → use T_THRESH_BASE (static)
) -> tuple:
    a_G = sig_4ch['a_G']
    a_A = sig_4ch['a_A']
    a_T = sig_4ch['a_T']

    G_mem = a_G.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    T_mem = a_T.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    fired = (a_A.shift(1).fillna(0.0) > A_FIRE_THRESH)

    gth = _dynamic_gth(rv_norm.reindex(sig_4ch.index, method='ffill').fillna(1.0), k_g)
    tth = T_THRESH_BASE if tth_dyn is None else tth_dyn.reindex(sig_4ch.index, method='ffill').fillna(T_THRESH_BASE)

    q_GH_TH = (fired & (G_mem > gth) & (T_mem > tth)).astype(float)
    q_GH_TL = (fired & (G_mem > gth) & (T_mem <= tth)).astype(float)
    q_GL_TH = (fired & (G_mem <= gth) & (T_mem > tth)).astype(float)
    q_GL_TL = (fired & (G_mem <= gth) & (T_mem <= tth)).astype(float)
    return q_GH_TH, q_GH_TL, q_GL_TH, q_GL_TL


def _build_pnl(
    base: pd.Series,
    sv36: pd.DataFrame,
    lf:   pd.DataFrame,
    s4:   pd.DataFrame,
    rv_norm: pd.Series,
    k_g:  float,
    tth_dyn: pd.Series | None = None,
) -> pd.Series:
    idx  = base.index
    sv36 = sv36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lf.reindex(idx,   method='ffill').fillna(0.5)
    s4   = s4.reindex(idx,   method='ffill').fillna(0.0)
    gam  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lp   = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size = np.clip(1.0 - gam, 0.0, 1.0) * (0.75 + 0.5 * lp)

    q_GH_TH, q_GH_TL, q_GL_TH, q_GL_TL = _make_quadrant_flags(
        s4, rv_norm, k_g, tth_dyn)

    phase = (1.0 + GH_TH*q_GH_TH + GH_TL*q_GH_TL
             + GL_TH*q_GL_TH + GL_TL*q_GL_TL).clip(0.05, CLIP)

    flag = (s4['a_G'].shift(1).fillna(0.0) > G_BOOST_THRESH).astype(float)
    return base.fillna(0.0) * size * (1.0 + CHAMPION_BOOST * flag) * phase


def _sharpe(pnl: pd.Series) -> float:
    return float(_stats(pnl)['sharpe'])

def _maxdd(pnl: pd.Series) -> float:
    return float(_stats(pnl)['max_dd'])


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    t0  = time.time()
    BAR = '=' * 100
    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)
    rng = np.random.default_rng(42)   # reproducible noise in stress test

    print(BAR)
    print("  v57 — MINIMUM VIABLE ROBUSTNESS VALIDATION")
    print("  3 tests: OOS split | Vol stress | T_THRESH coupling")
    print(f"  K=0.10 FROZEN. No new parameters introduced.")
    print(BAR)

    t = lambda msg: print(f'\n{msg}', flush=True)

    # ── Data + signals (identical pipeline to v55) ────────────────────────────
    t('[1] 1h data')
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_mask   = df_1h.index >= TEST_START          # 2023-01-01 onward
    train_1h    = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)

    # OOS sub-masks (within the test window)
    first_half  = (df_1h.index >= TEST_START)    & (df_1h.index < OOS_SPLIT)  # 2023-2024
    second_half = (df_1h.index >= OOS_SPLIT)                                   # 2025-2026

    t(f'[2] Funding  t={time.time()-t0:.0f}s')
    try:
        fund = _cached_fetch_binance_funding()
        fund_eth = fund.get('ETHUSDT'); fund_btc = fund.get('BTCUSDT')
    except Exception as e:
        print(f'    Warning: {e}'); fund_eth = fund_btc = None

    t(f'[3] State panel  t={time.time()-t0:.0f}s')
    X = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X = np.nan_to_num(X)
    train_idx   = np.where(train_1h)[0]
    calib_mask  = np.zeros(len(df_1h), dtype=bool)
    calib_mask[train_idx[-CALIB_BARS:]] = True

    t(f'[4] Engine  t={time.time()-t0:.0f}s')
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(
        X, calib_mask)
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
    print(f"    v34 base Sharpe (full test): {_sharpe(base_pnl[test_mask]):+.3f}")

    # ── rv_norm (frozen K=0.10) ───────────────────────────────────────────────
    rv_norm    = _realized_vol(df_1h)
    gth_series = _dynamic_gth(rv_norm, k_g=0.10)   # for test 3

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 1 — OOS SPLIT
    # ─────────────────────────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  TEST 1 — OUT-OF-SAMPLE SPLIT')
    print(f'  K=0.10 frozen. Evaluate: full (2023-2026), first_half (2023-2024), second_half (2025-2026)')
    print(f'  Pass criterion: second_half Sharpe ≥ 3.60')
    print(f'{BAR}')

    pnl_v54 = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch, rv_norm, k_g=0.00)
    pnl_v55 = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch, rv_norm, k_g=0.10)

    oos1_results = {}
    print(f"\n  {'Config':<18} {'Full 2023-26':>13} {'First 23-24':>13} {'Second 25-26':>14} {'MaxDD':>8}")
    print(f"  {'-'*18} {'-'*13} {'-'*13} {'-'*14} {'-'*8}")
    for name, pnl in [('v54 (K=0.00)', pnl_v54), ('v55 (K=0.10)', pnl_v55)]:
        s_full  = _sharpe(pnl[test_mask])
        s_first = _sharpe(pnl[first_half])
        s_sec   = _sharpe(pnl[second_half])
        dd_sec  = _maxdd(pnl[second_half])
        flag    = '  ✓ PASS' if (s_sec >= 3.60 and name.startswith('v55')) else ''
        print(f"  {name:<18} {s_full:>+13.4f} {s_first:>+13.4f} {s_sec:>+14.4f} {dd_sec:>+7.1%}{flag}")
        oos1_results[name] = {
            'sharpe_full': s_full, 'sharpe_first': s_first, 'sharpe_second': s_sec,
            'maxdd_second': dd_sec,
        }

    sec_half_v55 = oos1_results['v55 (K=0.10)']['sharpe_second']
    sec_half_v54 = oos1_results['v54 (K=0.00)']['sharpe_second']
    delta_oos    = sec_half_v55 - sec_half_v54
    t1_pass = sec_half_v55 >= 3.60
    print(f"\n  v55 second_half: {sec_half_v55:+.4f}")
    print(f"  v55 vs v54 on second_half: {delta_oos:+.4f}")
    print(f"  TEST 1 RESULT: {'PASS  (≥ 3.60)' if t1_pass else 'FAIL  (< 3.60)'}")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 2 — VOLATILITY INPUT STRESS
    # ─────────────────────────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  TEST 2 — VOLATILITY INPUT STRESS')
    print('  Scale or perturb rv_norm fed to the dynamic G_THRESH formula.')
    print('  Pass criterion: all Sharpe drops vs baseline (K=0.10) < 0.15')
    print(f'{BAR}')

    baseline_sharpe = _sharpe(pnl_v55[test_mask])

    stress_configs = {
        'baseline  (K=0.10)':  rv_norm,
        'rv × 0.90':           rv_norm * 0.90,
        'rv × 1.10':           rv_norm * 1.10,
        'rv + N(0,0.02)':      (rv_norm + rng.normal(0, 0.02, size=len(rv_norm))).clip(0.02, None),
    }

    stress_results = {}
    print(f"\n  {'Config':<28} {'Sharpe':>8} {'Δ_baseline':>12} {'MaxDD':>8} {'Verdict':>10}")
    print(f"  {'-'*28} {'-'*8} {'-'*12} {'-'*8} {'-'*10}")
    t2_pass = True
    for name, rv_perturbed in stress_configs.items():
        pnl_s = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch,
                            rv_perturbed, k_g=0.10)
        s = _sharpe(pnl_s[test_mask])
        d = s - baseline_sharpe
        dd = _maxdd(pnl_s[test_mask])
        is_baseline = name.startswith('baseline')
        verdict = '—' if is_baseline else ('PASS' if abs(d) < 0.15 else 'FAIL')
        if not is_baseline and abs(d) >= 0.15:
            t2_pass = False
        print(f"  {name:<28} {s:>+8.4f} {d:>+12.4f} {dd:>+7.1%}  {verdict:>8}")
        stress_results[name] = {'sharpe': s, 'delta': d, 'maxdd': dd}

    max_drop = max(abs(v['delta']) for k, v in stress_results.items()
                   if not k.startswith('baseline'))
    print(f"\n  Max absolute drop across perturbations: {max_drop:.4f}")
    print(f"  TEST 2 RESULT: {'PASS  (max drop < 0.15)' if t2_pass else 'FAIL  (max drop ≥ 0.15)'}")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 3 — COHERENT T_THRESH COUPLING
    # ─────────────────────────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  TEST 3 — COHERENT T_THRESH COUPLING  (discovery, not optimisation)')
    print('  Formula: tth = 0.41 + 0.01 * (gth_dyn / G_THRESH_BASE - 1)')
    print('  Interpretation: link T loosely to G state so both thresholds move together.')
    print('  Pass: Sharpe > v55 baseline → real upgrade path found.')
    print('  Fail: keep current config — no harm done.')
    print(f'{BAR}')

    # Compute dynamic T_THRESH from the SAME rv_norm signal
    # gth_dyn / 0.45 = 1 + K*(1-rv_norm), so tth = 0.41 + 0.01*(K*(1-rv_norm))
    # Never let tth stray far from 0.41 — clip to [0.38, 0.44]
    tth_dyn = (T_THRESH_BASE + 0.01 * (gth_series / G_THRESH_BASE - 1.0)).clip(0.38, 0.44)

    pnl_t3 = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch,
                         rv_norm, k_g=0.10, tth_dyn=tth_dyn)
    s_t3  = _sharpe(pnl_t3[test_mask])
    dd_t3 = _maxdd(pnl_t3[test_mask])
    delta_t3 = s_t3 - baseline_sharpe

    # Also measure on second half specifically
    s_t3_sec = _sharpe(pnl_t3[second_half])

    print(f"\n  {'Config':<32} {'Full Sharpe':>12} {'Δ_v55':>10} {'Second-half':>12} {'MaxDD':>8}")
    print(f"  {'-'*32} {'-'*12} {'-'*10} {'-'*12} {'-'*8}")
    print(f"  {'v55 baseline (static tth)':<32} {baseline_sharpe:>+12.4f} {'—':>10} {sec_half_v55:>+12.4f} {_maxdd(pnl_v55[test_mask]):>+7.1%}")
    print(f"  {'v55 + dynamic tth (test3)':<32} {s_t3:>+12.4f} {delta_t3:>+10.4f} {s_t3_sec:>+12.4f} {dd_t3:>+7.1%}")

    t3_improves = delta_t3 > 0.0
    t3_verdict  = 'IMPROVED — upgrade path exists; run dedicated sweep' if t3_improves else 'NO GAIN — keep static T_THRESH=0.41'
    print(f"\n  tth range: [{tth_dyn.min():.4f}, {tth_dyn.max():.4f}]")
    print(f"  Δ v55 baseline: {delta_t3:+.4f}")
    print(f"  TEST 3 RESULT: {t3_verdict}")

    # ─────────────────────────────────────────────────────────────────────────
    # SUMMARY
    # ─────────────────────────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  VALIDATION SUMMARY')
    print(f'{BAR}')
    print(f"""
  Test 1 — OOS split       : {'✓ PASS' if t1_pass else '✗ FAIL'}
    v55 second_half Sharpe : {sec_half_v55:+.4f}  (threshold 3.60)
    v55 vs v54 on 25-26    : {delta_oos:+.4f}

  Test 2 — Vol stress      : {'✓ PASS' if t2_pass else '✗ FAIL'}
    Max Sharpe drop        : {max_drop:.4f}  (threshold 0.15)

  Test 3 — T_THRESH link   : {'IMPROVED' if t3_improves else 'NO GAIN'}
    Δ vs v55 baseline      : {delta_t3:+.4f}
""")

    passes = sum([t1_pass, t2_pass])
    if passes == 2 and t3_improves:
        overall = "LOCK v55 + follow up on T coupling in v58"
    elif passes == 2:
        overall = "LOCK v55 — move to paper trading / live sim"
    elif passes == 1:
        overall = "KEEP v55, reduce position size — partial trust"
    else:
        overall = "REVERT to v54 — v55 not reliable enough"
    print(f"  OVERALL DECISION: {overall}")
    print(f'\n{BAR}')

    # ── Save results ──────────────────────────────────────────────────────────
    results = {
        'meta': {
            'v54_sharpe': V54_SHARPE,
            'v55_sharpe': V55_SHARPE,
            'k_g_frozen': 0.10,
            'oos_split_date': OOS_SPLIT,
        },
        'test1_oos_split': {
            'pass': t1_pass,
            'pass_threshold': 3.60,
            'v55_second_half_sharpe': float(sec_half_v55),
            'v54_second_half_sharpe': float(sec_half_v54),
            'delta_v55_vs_v54_oos': float(delta_oos),
            'detail': oos1_results,
        },
        'test2_vol_stress': {
            'pass': t2_pass,
            'pass_threshold_drop': 0.15,
            'max_absolute_drop': float(max_drop),
            'detail': {k: {kk: float(vv) for kk, vv in v.items()}
                       for k, v in stress_results.items()},
        },
        'test3_tth_coupling': {
            'improves': t3_improves,
            'delta_vs_v55': float(delta_t3),
            'v55_baseline_sharpe': float(baseline_sharpe),
            'coupled_full_sharpe': float(s_t3),
            'coupled_second_half_sharpe': float(s_t3_sec),
            'tth_range': [float(tth_dyn.min()), float(tth_dyn.max())],
            'verdict': t3_verdict,
        },
        'overall': {
            'tests_passed': passes,
            'test3_improves': t3_improves,
            'decision': overall,
        },
    }

    out_path = OUT_DIR_ / 'crypto_bsdt_v57_validation.json'
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"  Results saved → {out_path}")
    print(f"  Total elapsed: {time.time()-t0:.1f}s")
    print(BAR)

    return results


if __name__ == '__main__':
    main()
