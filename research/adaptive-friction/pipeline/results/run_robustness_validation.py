"""
Crypto BSDT — Robustness Validation + Ensemble
===============================================
Final plateau champion (v54):
  clip=6.0, GH_TH=5.0, GH_TL=-1.00, GL_TH=-1.00, GL_TL=-1.00
  G_THRESH=0.45, T_THRESH=0.41, N=8
  G_BOOST_THRESH=0.45, CHAMPION_BOOST=0.65, A_FIRE_THRESH=0.65
  Sharpe=+3.857  MaxDD=-3.7%

Purpose:
  1. ENSEMBLE — average PnL of plateau region configs (not single winner)
  2. SENSITIVITY — perturb each param ±small, check Sharpe stays stable
  3. REGIME SPLIT — per-year Sharpe + high/low vol regime breakdown
  4. TRADE STATS — check trade count, duration, tail behavior

This is the validation gate before deploying.
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

# ── cache helpers (identical to v54) ─────────────────────────────────────────
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


# ── plateau region definition ────────────────────────────────────────────────
# These are the confirmed stable members from v52–v54 plateau.
# ALL have Sharpe within 0.07 of champion — this IS the invariance zone.

PLATEAU_CONFIGS = {
    # name                 clip   tth    aft    cb     gbt   gth
    'prod_core':          (6.0,  0.41,  0.65,  0.65,  0.45, 0.45),
    'prod_clip55_tth041': (5.5,  0.41,  0.65,  0.65,  0.45, 0.45),
    'prod_clip60_tth040': (6.0,  0.40,  0.65,  0.65,  0.45, 0.45),
    'prod_clip55_tth040': (5.5,  0.40,  0.65,  0.65,  0.45, 0.45),
    'prod_gth046':        (6.0,  0.41,  0.65,  0.65,  0.45, 0.46),
    'prod_cb063':         (6.0,  0.41,  0.65,  0.63,  0.45, 0.45),
    'prod_cb067':         (6.0,  0.41,  0.65,  0.67,  0.45, 0.45),
    'prod_aft066':        (6.0,  0.41,  0.66,  0.65,  0.45, 0.45),
}

# Sensitivity perturbations (around core config)
SENSITIVITY_AXES = {
    'clip-0.5': dict(clip=5.5),  'clip+0.5': dict(clip=6.5),
    'clip+1.0': dict(clip=7.0),
    'tth-0.01': dict(tth=0.40),  'tth+0.01': dict(tth=0.42),
    'tth-0.02': dict(tth=0.39),  'tth+0.02': dict(tth=0.43),
    'aft-0.01': dict(aft=0.64),  'aft+0.01': dict(aft=0.66),
    'aft-0.02': dict(aft=0.63),  'aft+0.02': dict(aft=0.67),
    'cb-0.05':  dict(cb=0.60),   'cb+0.05':  dict(cb=0.70),
    'gbt-0.03': dict(gbt=0.42),  'gbt+0.03': dict(gbt=0.48),
    'gth-0.01': dict(gth=0.44),  'gth+0.01': dict(gth=0.46),
}

GH_TL_OPT = GL_TH_OPT = GL_TL_OPT = -1.00
N_OPT = 8
CORE = dict(clip=6.0, tth=0.41, aft=0.65, cb=0.65, gbt=0.45, gth=0.45)


# ── quadrant flags ────────────────────────────────────────────────────────────
def _make_quadrant_flags(s4, g_thresh, t_thresh, n, aft):
    a_G = s4['a_G']; a_A = s4['a_A']; a_T = s4['a_T']
    G_mem = a_G.rolling(n, min_periods=1).max().shift(1).fillna(0.0)
    T_mem = a_T.rolling(n, min_periods=1).max().shift(1).fillna(0.0)
    fired = (a_A.shift(1).fillna(0.0) > aft)
    q_GH_TH = (fired & (G_mem > g_thresh) & (T_mem > t_thresh)).astype(float)
    q_GH_TL = (fired & (G_mem > g_thresh) & (T_mem <= t_thresh)).astype(float)
    q_GL_TH = (fired & (G_mem <= g_thresh) & (T_mem > t_thresh)).astype(float)
    q_GL_TL = (fired & (G_mem <= g_thresh) & (T_mem <= t_thresh)).astype(float)
    return q_GH_TH, q_GH_TL, q_GL_TH, q_GL_TL


def _build_pnl(base, sv36, lf, s4, clip, tth, aft, cb, gbt, gth):
    idx = base.index
    sv36 = sv36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lf.reindex(idx, method='ffill').fillna(0.5)
    s4   = s4.reindex(idx, method='ffill').fillna(0.0)
    gam  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lp   = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size = np.clip(1.0 - gam, 0.0, 1.0) * (0.75 + 0.5 * lp)
    q_GH_TH, q_GH_TL, q_GL_TH, q_GL_TL = _make_quadrant_flags(s4, gth, tth, N_OPT, aft)
    phase = (1.0 + (clip-1)*q_GH_TH + GH_TL_OPT*q_GH_TL
             + GL_TH_OPT*q_GL_TH + GL_TL_OPT*q_GL_TL).clip(0.05, clip)
    flag  = (s4['a_G'].shift(1).fillna(0.0) > gbt).astype(float)
    return base.fillna(0.0) * size * (1.0 + cb * flag) * phase


def _regime_stats(pnl: pd.Series, vol_series: pd.Series) -> dict:
    """Split test PnL by year and by realized-vol regime."""
    out = {}
    # Per-year
    for yr in sorted(pnl.index.year.unique()):
        mask = pnl.index.year == yr
        s = _stats(pnl[mask])
        out[f'year_{yr}'] = s['sharpe']
    # Vol regime: split into 2 halves by median realized vol
    med_vol = vol_series.median()
    lo = pnl[vol_series <= med_vol]
    hi = pnl[vol_series >  med_vol]
    out['low_vol']  = _stats(lo)['sharpe']
    out['high_vol'] = _stats(hi)['sharpe']
    return out


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    t0 = time.time()
    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)
    BAR = '='*100

    print(BAR)
    print("  ROBUSTNESS VALIDATION + ENSEMBLE")
    print("  Final plateau: clip=6.0, tth=0.41, aft=0.65, cb=0.65, gbt=0.45, gth=0.45")
    print("  Sharpe=+3.857  — verifying stability before deployment")
    print(BAR)

    t = lambda msg: print(f'\n{msg}', flush=True)

    t('[1] 1h data')
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_1h  = df_1h.index >= TEST_START
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    print(f'    bars={len(df_1h):,}  train={train_1h.sum():,}  test={test_1h.sum():,}')

    t(f'[2] Funding t={time.time()-t0:.0f}s')
    try:
        fund = _cached_fetch_binance_funding()
        fund_eth = fund.get('ETHUSDT'); fund_btc = fund.get('BTCUSDT')
    except Exception as e:
        print(f'    Warning: {e}'); fund_eth = fund_btc = None

    t(f'[3] State panel t={time.time()-t0:.0f}s')
    X = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X = np.nan_to_num(X)
    train_idx = np.where(train_1h)[0]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[train_idx[-CALIB_BARS:]] = True

    t(f'[4] Engine t={time.time()-t0:.0f}s')
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(X, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)
    M_k1 = MasterOperator.calibrate(X[calib_mask], k=PCA_K_B)

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
    test_mask = base_pnl.index >= TEST_START
    print(f"    v34 Sharpe: {_stats(base_pnl[test_mask])['sharpe']:+.3f}")

    # realized vol on test window for regime split
    rv_test = df_1h['ret_eth'].rolling(168, min_periods=24).std()
    rv_test = rv_test[test_mask]

    def _pnl(cfg):
        c = {**CORE, **cfg}
        return _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch,
                          c['clip'], c['tth'], c['aft'], c['cb'], c['gbt'], c['gth'])

    # ── 1. PLATEAU ENSEMBLE ────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  SECTION 1: PLATEAU ENSEMBLE')
    print(f'{BAR}')

    plateau_pnls = {}
    plateau_stats = {}
    for name, (clip, tth, aft, cb, gbt, gth) in PLATEAU_CONFIGS.items():
        p = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch,
                       clip, tth, aft, cb, gbt, gth)
        plateau_pnls[name] = p
        s = _stats(p[test_mask])
        plateau_stats[name] = s
        print(f"  {name:<30} Sharpe={s['sharpe']:+.4f}  MaxDD={s['max_dd']:+.1%}  CAGR={s['cagr']:+.1%}")

    # Ensemble = equal-weight average of all plateau members
    ensemble_pnl = pd.concat(list(plateau_pnls.values()), axis=1).mean(axis=1)
    es = _stats(ensemble_pnl[test_mask])
    print(f"\n  {'ENSEMBLE (equal weight)':<30} Sharpe={es['sharpe']:+.4f}  "
          f"MaxDD={es['max_dd']:+.1%}  CAGR={es['cagr']:+.1%}")

    # Also show core alone
    core_pnl = _pnl({})
    cs = _stats(core_pnl[test_mask])
    print(f"  {'CORE (single config)':<30} Sharpe={cs['sharpe']:+.4f}  "
          f"MaxDD={cs['max_dd']:+.1%}  CAGR={cs['cagr']:+.1%}")

    sharpe_values = [v['sharpe'] for v in plateau_stats.values()]
    print(f"\n  Plateau Sharpe range: [{min(sharpe_values):+.4f}, {max(sharpe_values):+.4f}]  "
          f"spread={max(sharpe_values)-min(sharpe_values):.4f}")
    print(f"  Ensemble vs Core delta: {es['sharpe']-cs['sharpe']:+.4f} Sharpe")

    _yoy_table('ensemble', ensemble_pnl)
    _yoy_table('core    ', core_pnl)

    # ── 2. SENSITIVITY ANALYSIS ────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  SECTION 2: SENSITIVITY (all perturbations applied to core config)')
    print(f'{BAR}')
    print(f"  {'Perturbation':<20} {'Sharpe':>8} {'Delta':>8} {'MaxDD':>8} {'Status'}")
    print(f"  {'-'*20} {'-'*8} {'-'*8} {'-'*8} {'-'*10}")

    core_sharpe = cs['sharpe']
    sens_results = {}
    for pname, pdict in SENSITIVITY_AXES.items():
        p = _pnl(pdict)
        s = _stats(p[test_mask])
        d = s['sharpe'] - core_sharpe
        status = '✓ STABLE' if abs(d) < 0.05 else ('~ MILD' if abs(d) < 0.15 else '✗ SENSITIVE')
        sens_results[pname] = {'sharpe': s['sharpe'], 'delta': d, 'maxdd': s['max_dd']}
        print(f"  {pname:<20} {s['sharpe']:>+8.4f} {d:>+8.4f} {s['max_dd']:>+7.1%}  {status}")

    deltas = [v['delta'] for v in sens_results.values()]
    print(f"\n  Sensitivity summary:")
    print(f"    Max adverse delta:  {min(deltas):+.4f}")
    print(f"    Max favorable delta:{max(deltas):+.4f}")
    print(f"    Avg abs delta:      {np.mean(np.abs(deltas)):.4f}")
    if np.mean(np.abs(deltas)) < 0.05:
        print("    => ROBUST: avg abs delta < 0.05 — plateau is genuine, not a spike")
    elif np.mean(np.abs(deltas)) < 0.10:
        print("    => MILD: small sensitivity — proceed with ensemble, not single config")
    else:
        print("    => WARNING: high sensitivity — overfit risk present")

    # ── 3. REGIME SPLIT ───────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  SECTION 3: REGIME STABILITY (core config)')
    print(f'{BAR}')
    regime = _regime_stats(core_pnl[test_mask], rv_test)
    ens_regime = _regime_stats(ensemble_pnl[test_mask], rv_test)

    print(f"\n  {'Period/Regime':<20} {'Core Sharpe':>12} {'Ensemble Sharpe':>16}")
    print(f"  {'-'*20} {'-'*12} {'-'*16}")
    for key in sorted(regime.keys()):
        c_sh = regime[key]
        e_sh = ens_regime.get(key, float('nan'))
        flag = ''
        if isinstance(c_sh, float) and c_sh < 1.0:
            flag = ' ⚠ LOW'
        elif isinstance(c_sh, float) and c_sh < 0:
            flag = ' ✗ NEGATIVE'
        print(f"  {key:<20} {c_sh:>+12.3f} {e_sh:>+16.3f}{flag}")

    yr_sharpes = [v for k, v in regime.items() if k.startswith('year_')]
    if len(yr_sharpes) > 1 and min(yr_sharpes) > 0.5:
        print("\n    => ALL YEARS POSITIVE: strategy not a single-year bet")
    else:
        print(f"\n    => WARNING: min annual Sharpe={min(yr_sharpes):.2f} — check specific year")

    lv = regime.get('low_vol', 0)
    hv = regime.get('high_vol', 0)
    if lv > 0.5 and hv > 0.5:
        print(f"    => BOTH VOL REGIMES POSITIVE: not a pure vol bet (lo={lv:.2f}, hi={hv:.2f})")
    else:
        print(f"    => WARNING: vol regime asymmetry (lo={lv:.2f}, hi={hv:.2f})")

    # ── 4. Save ────────────────────────────────────────────────────────────
    print(f'\n{BAR}')
    results_out = {
        'ensemble_sharpe':  float(es['sharpe']),
        'ensemble_maxdd':   float(es['max_dd']),
        'ensemble_cagr':    float(es['cagr']),
        'core_sharpe':      float(cs['sharpe']),
        'core_maxdd':       float(cs['max_dd']),
        'plateau_spread':   float(max(sharpe_values)-min(sharpe_values)),
        'avg_abs_sensitivity': float(np.mean(np.abs(deltas))),
        'max_adverse_sensitivity': float(min(deltas)),
        'regime_breakdown': {k: float(v) for k, v in regime.items()},
        'ensemble_regime':  {k: float(v) for k, v in ens_regime.items()},
        'plateau_members':  {k: {'sharpe': float(v['sharpe']), 'maxdd': float(v['max_dd'])}
                             for k, v in plateau_stats.items()},
    }
    out_path = OUT_DIR_ / 'robustness_validation.json'
    with open(out_path, 'w') as f:
        json.dump(results_out, f, indent=2)

    print(f"\n  ROBUSTNESS REPORT SAVED -> {out_path}")
    print(f"  Total elapsed: {time.time()-t0:.1f}s")
    print(BAR)


if __name__ == '__main__':
    main()
