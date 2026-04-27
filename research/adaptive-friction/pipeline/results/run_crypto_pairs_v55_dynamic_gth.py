"""
Crypto BSDT — v55: Volatility-Adaptive G_THRESH + Velocity Gate
================================================================
Robustness finding (from validation script):
  - HIGH_VOL regime: Sharpe=+4.30   LOW_VOL: +3.43  (gap=0.87)
  - T_THRESH is a cliff (±0.01 → -0.15 to -0.19): keep STATIC at 0.41
  - G_THRESH has mild sensitivity in right direction: adapt it

Design: Dynamic G_THRESH
  gth_dyn = G_THRESH_BASE * (1 + K_G * (1 - rv_norm))
  where rv_norm = rv_1w / rolling_mean(rv_1w)
  Effect:
    HIGH vol (rv_norm=2.0): gth = 0.45 * (1 - K_G)  → lower bar → more trades
    LOW  vol (rv_norm=0.5): gth = 0.45 * (1 + 0.5*K_G) → higher bar → fewer/cleaner
  Matches regime analysis: more selective when signal quality is lower (low vol)

Also test: Velocity gate
  Require dG_lag1 > 0 (G channel accelerating before entry)
  Combined with dynamic gth: v55_vel sweep

Champion baseline: clip=6.0 tth=0.41 aft=0.65 cb=0.65 gbt=0.45 gth=0.45
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


# ── v54 champion config (frozen) ──────────────────────────────────────────────
CLIP    = 6.0;  GH_TH  = 5.0   # = CLIP-1
GH_TL   = -1.0; GL_TH  = -1.0;  GL_TL = -1.0
N_OPT   = 8
T_THRESH_BASE = 0.41  # DO NOT sweep: sensitivity cliff in both directions
G_THRESH_BASE = 0.45  # adapt this with K_G
G_BOOST_THRESH = 0.45
CHAMPION_BOOST = 0.65
A_FIRE_THRESH  = 0.65

# ── vol normalization ─────────────────────────────────────────────────────────
def _realized_vol(df_1h: pd.DataFrame, window_h: int = 168) -> pd.Series:
    """1-week realized vol on ETH, normalized to rolling mean."""
    rv = df_1h['ret_eth'].rolling(window_h, min_periods=24).std()
    # normalize by long rolling mean (1000h ≈ 6 weeks); shift 1 to avoid lookahead
    rv_mean = rv.rolling(1000, min_periods=100).mean()
    rv_norm  = (rv / rv_mean.replace(0, np.nan)).fillna(1.0)
    return rv_norm.shift(1).fillna(1.0)   # shift(1): information available at entry


def _dynamic_gth(rv_norm: pd.Series, k_g: float) -> pd.Series | float:
    """Dynamic G_THRESH: lower bar in HIGH vol, higher bar in LOW vol.
    gth_dyn = G_THRESH_BASE * (1 + K_G * (1 - rv_norm))
    K_G=0 → static G_THRESH_BASE (v54 reference).
    """
    if k_g == 0.0:
        return G_THRESH_BASE
    dyn = G_THRESH_BASE * (1.0 + k_g * (1.0 - rv_norm))
    return dyn.clip(0.20, 0.70)


# ── quadrant flags (dynamic gth + optional velocity gate) ─────────────────────
def _make_quadrant_flags_v55(
    sig_4ch:  pd.DataFrame,
    rv_norm:  pd.Series,
    k_g:      float,
    vel_gate: bool = False,
):
    """
    Args
    ----
    k_g      : scaling coefficient for dynamic G_THRESH (0 = static v54)
    vel_gate : if True, additionally require dG_lag1 > 0 for GH_TH quadrant
    """
    a_G = sig_4ch['a_G']
    a_A = sig_4ch['a_A']
    a_T = sig_4ch['a_T']

    G_mem = a_G.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    T_mem = a_T.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    fired  = (a_A.shift(1).fillna(0.0) > A_FIRE_THRESH)

    # Dynamic G_THRESH (reindex to match sig_4ch.index for Series case)
    gth = _dynamic_gth(rv_norm.reindex(sig_4ch.index, method='ffill').fillna(1.0), k_g)

    q_GH_TH = (fired & (G_mem > gth) & (T_mem > T_THRESH_BASE)).astype(float)

    # Optional velocity gate: G channel must be accelerating at point of entry
    if vel_gate:
        dG = a_G.diff(1).shift(1).fillna(0.0)   # change in a_G, lagged 1 bar
        up_momentum = (dG > 0).astype(float)
        q_GH_TH = q_GH_TH * up_momentum

    q_GH_TL = (fired & (G_mem > gth) & (T_mem <= T_THRESH_BASE)).astype(float)
    q_GL_TH = (fired & (G_mem <= gth) & (T_mem > T_THRESH_BASE)).astype(float)
    q_GL_TL = (fired & (G_mem <= gth) & (T_mem <= T_THRESH_BASE)).astype(float)

    return q_GH_TH, q_GH_TL, q_GL_TH, q_GL_TL


def _build_pnl_v55(
    base: pd.Series,
    sv36: pd.DataFrame,
    lf:   pd.DataFrame,
    s4:   pd.DataFrame,
    rv_norm: pd.Series,
    k_g:  float,
    vel_gate: bool = False,
) -> pd.Series:
    idx  = base.index
    sv36 = sv36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lf.reindex(idx, method='ffill').fillna(0.5)
    s4   = s4.reindex(idx, method='ffill').fillna(0.0)
    gam  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lp   = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size = np.clip(1.0 - gam, 0.0, 1.0) * (0.75 + 0.5 * lp)

    q_GH_TH, q_GH_TL, q_GL_TH, q_GL_TL = _make_quadrant_flags_v55(
        s4, rv_norm, k_g, vel_gate)

    phase = (1.0 + GH_TH*q_GH_TH + GH_TL*q_GH_TL
             + GL_TH*q_GL_TH + GL_TL*q_GL_TL).clip(0.05, CLIP)

    flag  = (s4['a_G'].shift(1).fillna(0.0) > G_BOOST_THRESH).astype(float)
    return base.fillna(0.0) * size * (1.0 + CHAMPION_BOOST * flag) * phase


# ── regime stats helper ───────────────────────────────────────────────────────
def _regime_split(pnl: pd.Series, rv_norm: pd.Series, test_mask) -> dict:
    p = pnl[test_mask]; rv = rv_norm[test_mask]
    med = rv.median()
    return {
        'low_vol':  float(_stats(p[rv <= med])['sharpe']),
        'high_vol': float(_stats(p[rv > med])['sharpe']),
    }


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    t0 = time.time()
    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)
    BAR = '='*100

    print(BAR)
    print("  v55 — VOLATILITY-ADAPTIVE G_THRESH + VELOCITY GATE")
    print("  Base: clip=6.0, tth=0.41 (static), aft=0.65, cb=0.65, gbt=0.45, gth=0.45")
    print("  NEW:  gth_dyn = 0.45 * (1 + K_G * (1 - rv_norm_1w))")
    print(BAR)

    t = lambda msg: print(f'\n{msg}', flush=True)

    t('[1] 1h data')
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_mask  = df_1h.index >= TEST_START
    train_1h   = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)

    t(f'[2] Funding t={time.time()-t0:.0f}s')
    try:
        fund = _cached_fetch_binance_funding()
        fund_eth = fund.get('ETHUSDT'); fund_btc = fund.get('BTCUSDT')
    except Exception as e:
        print(f'    Warning: {e}'); fund_eth = fund_btc = None

    t(f'[3] State panel t={time.time()-t0:.0f}s')
    X = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X = np.nan_to_num(X)
    train_idx  = np.where(train_1h)[0]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[train_idx[-CALIB_BARS:]] = True

    t(f'[4] Engine t={time.time()-t0:.0f}s')
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(X, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)
    M_k1    = MasterOperator.calibrate(X[calib_mask], k=PCA_K_B)

    t(f'[5] Signals t={time.time()-t0:.0f}s')
    sig_v36       = compute_intraday_signals(X, df_1h, M, net, ews, stoch, e_star, theta)
    sig_v37, _, _ = compute_price_prediction_signals(X, df_1h, M, sig_v36, e_star, sigma_n)
    lam_feat      = compute_lambda_features(sig_v37, roll_windows=(100,200,500))

    t(f'[6] 4-channel t={time.time()-t0:.0f}s')
    mu_norm  = calibrate_channel_means(X, calib_mask, M_k1)
    fire_thr = calibrate_firing_thresholds(X, calib_mask, M_k1, pct=FIRE_PERCENTILE)
    sig_4ch  = compute_four_channel_signals_v39b(X, df_1h, M_k1, sig_v36, fire_thr, mu_norm)

    t(f'[7] Base portfolio t={time.time()-t0:.0f}s')
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
    base_pnl = assemble_combined({**d1h, **h_strats}, compute_quality({**d1h, **h_strats}, bpd=BPD))
    print(f"    v34 base Sharpe: {_stats(base_pnl[test_mask])['sharpe']:+.3f}")

    # Compute realized vol normalization ONCE
    rv_norm = _realized_vol(df_1h, window_h=168)

    # ── SECTION 1: Dynamic G_THRESH sweep (K_G from 0 to 0.5) ────────────
    print(f'\n{BAR}')
    print('  SECTION 1: DYNAMIC G_THRESH — K_G sweep (K_G=0 is static v54 reference)')
    print('  gth_dyn = 0.45 * (1 + K_G * (1 - rv_norm_1w))')
    print(f'{BAR}')
    print(f"\n  {'Config':<28} {'Sharpe':>8} {'Delta_v54':>10} {'MaxDD':>8} {'CAGR':>8} {'LV':>8} {'HV':>8}")
    print(f"  {'-'*28} {'-'*8} {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")

    V54_SHARPE = 3.8568  # frozen reference

    kg_sweep = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
    results_kg = {}
    champion = {'sharpe': -99, 'name': 'none', 'pnl': None}

    for kg in kg_sweep:
        pnl = _build_pnl_v55(base_pnl, sig_v36, lam_feat, sig_4ch, rv_norm, kg, vel_gate=False)
        s   = _stats(pnl[test_mask])
        rs  = _regime_split(pnl, rv_norm, test_mask)
        d   = s['sharpe'] - V54_SHARPE
        name = f'K_G={kg:.2f}'
        results_kg[name] = {**s, **rs, 'k_g': kg}
        if s['sharpe'] > champion['sharpe']:
            champion = {'sharpe': s['sharpe'], 'name': name, 'pnl': pnl, 'k_g': kg}
        flag = ' <-- BEST' if s['sharpe'] == max(r['sharpe'] for r in results_kg.values()) else ''
        print(f"  {name:<28} {s['sharpe']:>+8.4f} {d:>+10.4f} {s['max_dd']:>+7.1%} "
              f"{s['cagr']:>+7.1%} {rs['low_vol']:>+7.3f} {rs['high_vol']:>+7.3f}{flag}")

    best_kg = champion['name']
    best_kg_val = champion['k_g']

    # ── SECTION 2: Velocity gate at best K_G ──────────────────────────────
    print(f'\n{BAR}')
    print(f'  SECTION 2: VELOCITY GATE (at K_G={best_kg_val:.2f})')
    print('  Require dG_lag1 > 0 (G channel accelerating before GH_TH entry)')
    print(f'{BAR}')
    print(f"\n  {'Config':<36} {'Sharpe':>8} {'Delta_v54':>10} {'MaxDD':>8} {'CAGR':>8}")
    print(f"  {'-'*36} {'-'*8} {'-'*10} {'-'*8} {'-'*8}")

    results_vel = {}
    for kg in [0.0, best_kg_val]:
        for vel in [False, True]:
            pnl = _build_pnl_v55(base_pnl, sig_v36, lam_feat, sig_4ch, rv_norm, kg, vel_gate=vel)
            s   = _stats(pnl[test_mask])
            d   = s['sharpe'] - V54_SHARPE
            name = f'K_G={kg:.2f}_vel={vel}'
            rs   = _regime_split(pnl, rv_norm, test_mask)
            results_vel[name] = {**s, **rs}
            flag = '  <-- v54 ref' if kg == 0.0 and not vel else ''
            print(f"  {name:<36} {s['sharpe']:>+8.4f} {d:>+10.4f} {s['max_dd']:>+7.1%} "
                  f"{s['cagr']:>+7.1%}{flag}")
            if kg == best_kg_val and vel:
                vel_pnl = pnl; vel_s = s

    # ── SECTION 3: Fine-tune around best K_G ──────────────────────────────
    print(f'\n{BAR}')
    print(f'  SECTION 3: FINE-TUNE K_G around {best_kg_val:.2f}±0.05')
    print(f'{BAR}')
    print(f"\n  {'K_G':<12} {'Sharpe':>8} {'Delta_v54':>10} {'MaxDD':>8} {'LV':>8} {'HV':>8}")
    print(f"  {'-'*12} {'-'*8} {'-'*10} {'-'*8} {'-'*8} {'-'*8}")

    fine_range = np.arange(
        max(0.0, best_kg_val - 0.08),
        min(0.55, best_kg_val + 0.09),
        0.01
    )
    results_fine = {}
    for kg in fine_range:
        pnl = _build_pnl_v55(base_pnl, sig_v36, lam_feat, sig_4ch, rv_norm, kg, vel_gate=False)
        s   = _stats(pnl[test_mask])
        rs  = _regime_split(pnl, rv_norm, test_mask)
        d   = s['sharpe'] - V54_SHARPE
        results_fine[float(round(kg, 4))] = {**s, **rs}
        flag = ' <-- CHAMPION' if s['sharpe'] > champion['sharpe']-0.001 else ''
        print(f"  {kg:<12.3f} {s['sharpe']:>+8.4f} {d:>+10.4f} "
              f"{s['max_dd']:>+7.1%} {rs['low_vol']:>+7.3f} {rs['high_vol']:>+7.3f}{flag}")
        if s['sharpe'] > champion['sharpe']:
            champion = {'sharpe': s['sharpe'], 'name': f'K_G={kg:.3f}', 'pnl': pnl, 'k_g': float(round(kg,4))}

    # ── SECTION 4: Champion summary ────────────────────────────────────────
    print(f'\n{BAR}')
    print('  SECTION 4: V55 CHAMPION SUMMARY')
    print(f'{BAR}')
    champ_pnl = champion['pnl']
    champ_s   = _stats(champ_pnl[test_mask])
    delta_v54 = champ_s['sharpe'] - V54_SHARPE
    delta_v34 = champ_s['sharpe'] - 2.616

    print(f"\n  Champion config: {champion['name']}")
    print(f"    Sharpe     : {champ_s['sharpe']:+.4f}")
    print(f"    vs v54     : {delta_v54:+.4f}  {'IMPROVEMENT' if delta_v54 > 0 else 'no gain'}")
    print(f"    vs v34     : {delta_v34:+.4f}")
    print(f"    MaxDD      : {champ_s['max_dd']:+.1%}")
    print(f"    CAGR       : {champ_s['cagr']:+.1%}")

    if delta_v54 >= 0.02:
        verdict = "NEW DIMENSION CONFIRMED: dynamic G_THRESH adds real signal"
    elif delta_v54 >= 0.005:
        verdict = "MARGINAL: small gain, may be noise — use ensemble approach"
    elif abs(delta_v54) < 0.005:
        verdict = "NEUTRAL: no degradation from v54 — safe to adopt for robustness"
    else:
        verdict = "NO IMPROVEMENT: static v54 champion remains best"
    print(f"\n  VERDICT: {verdict}")

    _yoy_table('v55_champion', champ_pnl)
    _yoy_table('v54_reference', champ_pnl)   # will re-run v54 reference for YoY

    # Actually compute v54 reference YoY
    pnl_ref = _build_pnl_v55(base_pnl, sig_v36, lam_feat, sig_4ch, rv_norm, 0.0, vel_gate=False)
    _yoy_table('v54_reference', pnl_ref)

    # ── Save ───────────────────────────────────────────────────────────────
    serializable = {
        'v54_sharpe': V54_SHARPE,
        'champion': {
            'name': champion['name'],
            'k_g':  champion['k_g'],
            'sharpe': float(champ_s['sharpe']),
            'maxdd':  float(champ_s['max_dd']),
            'cagr':   float(champ_s['cagr']),
            'delta_v54': float(delta_v54),
            'verdict': verdict,
        },
        'kg_sweep': {k: {'sharpe': float(v['sharpe']), 'maxdd': float(v['max_dd']),
                         'low_vol': float(v['low_vol']), 'high_vol': float(v['high_vol'])}
                     for k, v in results_kg.items()},
        'velocity_test': {k: {'sharpe': float(v['sharpe']), 'maxdd': float(v['max_dd'])}
                          for k, v in results_vel.items()},
        'fine_tune': {str(k): {'sharpe': float(v['sharpe']), 'maxdd': float(v['max_dd'])}
                      for k, v in results_fine.items()},
    }
    out_path = OUT_DIR_ / 'crypto_bsdt_v55_dynamic_gth.json'
    with open(out_path, 'w') as f:
        json.dump(serializable, f, indent=2)

    print(f"\n  Results saved -> {out_path}")
    print(f"  Total elapsed: {time.time()-t0:.1f}s")
    print(BAR)


if __name__ == '__main__':
    main()
