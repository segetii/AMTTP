"""
Crypto BSDT v51 — GH_TL deep-sweep below -0.80 at v50 champion baseline
=========================================================================
v50 champion: v50_E_ghtlm080_aft067_cb060  Sharpe=+3.7172
  (clip=5.0, GH_TH=4.0, GH_TL=-0.80, GL_TH=-1.00, GL_TL=-1.00,
   G_THRESH=0.45, T_THRESH=0.40, N_G=N_T=8,
   G_BOOST_THRESH=0.45, CHAMPION_BOOST=0.60, A_FIRE_THRESH=0.67)

Key v50 findings:
  - GH_TL Group A solo (aft=0.65): STILL MONOTONE at -1.00 (+3.7091 best)
  - GH_TL Group E joint: peak at -0.80 with aft=0.67 (+3.7172) — only tested to -0.80!
  - A_FIRE_THRESH: shifted to 0.67 (vs 0.65 in v49); discontinuity at 0.66
  - CHAMPION_BOOST: extremely flat 0.56-0.65, 0.60 fine
  - G_BOOST_THRESH: 0.45 confirmed optimal

v51 strategy:
  - Extend GH_TL joint sweep BELOW -0.80 (down to -1.00) with aft=0.67
  - Fine-tune A_FIRE_THRESH around 0.67 at new ghtl=-0.80 baseline
  - Confirm CHAMPION_BOOST peak at v50 baseline
  - Joint grid: GH_TL {-0.80 to -1.00} x aft {0.66-0.68} x cb {0.59-0.61}

Fixed throughout (v50 confirmed):
  clip=5.0, GH_TH=4.0, GL_TH=-1.00, GL_TL=-1.00
  G_THRESH=0.45, T_THRESH=0.40, N_G=N_T=8, G_BOOST_THRESH=0.45

Group A: GH_TL deep-sweep at v50 full baseline (gbt=0.45, cb=0.60, aft=0.67)
  GH_TL in {-1.00, -0.97, -0.95, -0.92, -0.90, -0.87, -0.85, -0.82, -0.80, -0.77}  -> 10 variants

Group B: A_FIRE_THRESH fine-tune at v50 champion (ghtl=-0.80, gbt=0.45, cb=0.60)
  AFT in {0.63, 0.64, 0.65, 0.66, 0.67, 0.68, 0.69, 0.70}   -> 8 variants

Group C: CHAMPION_BOOST confirm at v50 champion (ghtl=-0.80, gbt=0.45, aft=0.67)
  CB in {0.56, 0.57, 0.58, 0.59, 0.60, 0.61, 0.62, 0.63}   -> 8 variants

Group D: Joint grid — GH_TL {-0.80 to -1.00} x aft {0.66,0.67,0.68} x cb {0.59,0.60,0.61}
  5 x 3 x 3 = 45 variants

Total: 10 + 8 + 8 + 45 = 71 variants
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

from collapse_geometry import MasterOperator, Snapshot
from run_crypto_pairs_v38_lambda_norm import compute_lambda_features
from run_crypto_pairs_v37_price_prediction import compute_price_prediction_signals
from run_crypto_pairs_v36_intraday_bsdt import (
    N_AGENTS, N_FEATURES, CALIB_BARS,
    BPD, ANN_1H,
    build_intraday_state_panel, calibrate_intraday_engine,
    compute_intraday_signals,
    _net_ret, _stats,
)
from run_crypto_pairs_v34_full_combined import (
    OUT_DIR, TEST_START, TRAIN_START, TRAIN_END,
    build_1h_df, fetch_and_prepare, fetch_binance_funding,
    add_cross_market_features, add_leverage_features,
    build_daily_positions, upsample_daily_to_1h_pnl,
    compute_1h_strategies, compute_quality, assemble_combined,
)
from run_crypto_pairs_v39_four_channels import (
    CH_C, CH_G, CH_A, CH_T, CH_NAMES,
    FIRE_PERCENTILE,
    calibrate_firing_thresholds,
    print_summary_table, _yoy_table,
)
from run_crypto_pairs_v39b_k1_scaled import (
    PCA_K_B, MU_FLOOR,
    calibrate_channel_means,
    compute_four_channel_signals_v39b,
)
import run_crypto_pairs_v34_full_combined as _v34mod

OUT_DIR_ = Path(OUT_DIR)

# -- Disk cache for network fetches -------------------------------------------
_CACHE_DIR = Path(r'C:\amttp\data')
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_CACHE_TTL_H = 72


def _make_cached_fetch(orig_fn):
    def _wrapper(symbol: str, start: str, end: str, interval: str = '1h') -> pd.Series:
        cache_path = _CACHE_DIR / f'klines_{symbol}_{interval}.pkl'
        if cache_path.exists():
            age_h = (time.time() - cache_path.stat().st_mtime) / 3600
            if age_h < _CACHE_TTL_H:
                s = pd.read_pickle(str(cache_path))
                print(f'  {symbol} {interval} [CACHE {age_h:.0f}h old] {len(s):,} bars')
                return s
        s = orig_fn(symbol, start, end, interval)
        if len(s) > 0:
            s.to_pickle(str(cache_path))
            print(f'  -> cached to {cache_path.name}')
        return s
    return _wrapper


def _cached_fetch_and_prepare():
    cache_path = _CACHE_DIR / 'daily_crypto_pairs.pkl'
    if cache_path.exists():
        age_h = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_h < _CACHE_TTL_H:
            df = pd.read_pickle(str(cache_path))
            print(f'  fetch_and_prepare [CACHE {age_h:.0f}h old] {len(df):,} rows')
            return df
    df = fetch_and_prepare()
    df.to_pickle(str(cache_path))
    return df


def _cached_add_cross_market(df):
    cache_path = _CACHE_DIR / 'cross_market_df.pkl'
    if cache_path.exists():
        age_h = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_h < _CACHE_TTL_H:
            result = pd.read_pickle(str(cache_path))
            if result.shape[0] == df.shape[0] and result.index[-1] == df.index[-1]:
                print(f'  add_cross_market_features [CACHE {age_h:.0f}h old]')
                return result
    result = add_cross_market_features(df)
    result.to_pickle(str(cache_path))
    return result


def _cached_fetch_binance_funding():
    cache_path = _CACHE_DIR / 'binance_funding.pkl'
    if cache_path.exists():
        age_h = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_h < _CACHE_TTL_H:
            import pickle as _pk
            with open(str(cache_path), 'rb') as _f:
                fund = _pk.load(_f)
            print(f'  fetch_binance_funding [CACHE {age_h:.0f}h old]')
            return fund
    fund = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
    import pickle as _pk
    with open(str(cache_path), 'wb') as _f:
        _pk.dump(fund, _f)
    return fund


# -- v50 champion baseline ---------------------------------------------------
GL_TH_OPT    = -1.00
GL_TL_OPT    = -1.00
GH_TH_OPT    = 4.00
CLIP_OPT     = 5.00
G_THRESH_OPT = 0.45
T_THRESH_OPT = 0.40
N_G_OPT      = 8
N_T_OPT      = 8
# v50 champion values (new baselines):
GH_TL_V50           = -0.80
G_BOOST_THRESH_V50  = 0.45
CHAMPION_BOOST_V50  = 0.60
A_FIRE_THRESH_V50   = 0.67

# Sweep ranges
GHTL_SWEEP_A  = [-1.00, -0.97, -0.95, -0.92, -0.90, -0.87, -0.85, -0.82, -0.80, -0.77]
AFT_SWEEP_B   = [0.63, 0.64, 0.65, 0.66, 0.67, 0.68, 0.69, 0.70]
CB_SWEEP_C    = [0.56, 0.57, 0.58, 0.59, 0.60, 0.61, 0.62, 0.63]
# Joint D grid
GHTL_D        = [-0.80, -0.85, -0.90, -0.95, -1.00]
AFT_D         = [0.66, 0.67, 0.68]
CB_D          = [0.59, 0.60, 0.61]


# =============================================================================
#  QUADRANT FLAGS
# =============================================================================
def _make_quadrant_flags(sig_4ch, g_thresh, t_thresh, n_g, n_t, a_fire_thresh):
    a_G_raw = sig_4ch['a_G']
    a_A_raw = sig_4ch['a_A']
    a_T_raw = sig_4ch['a_T']
    G_mem = a_G_raw.rolling(n_g, min_periods=1).max().shift(1).fillna(0.0)
    T_mem = a_T_raw.rolling(n_t, min_periods=1).max().shift(1).fillna(0.0)
    A_fire_lag1 = (a_A_raw.shift(1).fillna(0.0) > a_fire_thresh)
    q_GH_TH = (A_fire_lag1 & (G_mem > g_thresh) & (T_mem > t_thresh)).astype(float)
    q_GH_TL = (A_fire_lag1 & (G_mem > g_thresh) & (T_mem <= t_thresh)).astype(float)
    q_GL_TH = (A_fire_lag1 & (G_mem <= g_thresh) & (T_mem > t_thresh)).astype(float)
    q_GL_TL = (A_fire_lag1 & (G_mem <= g_thresh) & (T_mem <= t_thresh)).astype(float)
    return q_GH_TH, q_GH_TL, q_GL_TH, q_GL_TL


def apply_v51_sizing(base_pnl, sig_v36, lam_feat, sig_4ch):
    idx  = base_pnl.index
    sv36 = sig_v36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lam_feat.reindex(idx, method='ffill').fillna(0.5)
    s4   = sig_4ch.reindex(idx, method='ffill').fillna(0.0)
    base = base_pnl.fillna(0.0)

    gam_adj  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lam_pct  = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size_sym = np.clip(1.0 - gam_adj, 0.0, 1.0) * (0.75 + 0.5 * lam_pct)

    def _quad_pnl(gh_tl, a_fire_thresh, g_boost_thresh, champion_boost) -> pd.Series:
        q_GH_TH, q_GH_TL, q_GL_TH, q_GL_TL = _make_quadrant_flags(
            s4, G_THRESH_OPT, T_THRESH_OPT, N_G_OPT, N_T_OPT, a_fire_thresh)
        phase = (1.0
                 + GH_TH_OPT * q_GH_TH
                 + gh_tl     * q_GH_TL
                 + GL_TH_OPT * q_GL_TH
                 + GL_TL_OPT * q_GL_TL).clip(0.05, CLIP_OPT)
        a_G_cur = s4['a_G'].shift(1).fillna(0.0)
        flag_aG = (a_G_cur > g_boost_thresh).astype(float)
        return base * size_sym * (1.0 + champion_boost * flag_aG) * phase

    pnl: dict[str, pd.Series] = {}

    # Reference points
    pnl['v48_champion_ref'] = _quad_pnl(-0.40, 0.70, 0.50, 0.50)
    pnl['v49_champion_ref'] = _quad_pnl(-0.60, 0.65, 0.45, 0.60)
    pnl['v50_champion_ref'] = _quad_pnl(-0.80, 0.67, 0.45, 0.60)

    # Group A: GH_TL deep-sweep at FULL v50 baseline
    for gh_tl in GHTL_SWEEP_A:
        sign = 'm'
        tl   = f'{abs(int(round(gh_tl * 100))):03d}'
        pnl[f'v51_A_ghtl{sign}{tl}'] = _quad_pnl(gh_tl,
                                                    A_FIRE_THRESH_V50,
                                                    G_BOOST_THRESH_V50,
                                                    CHAMPION_BOOST_V50)

    # Group B: A_FIRE_THRESH fine-tune at v50 champion (ghtl=-0.80)
    for aft in AFT_SWEEP_B:
        ta = f'{int(round(aft * 100)):03d}'
        pnl[f'v51_B_aft{ta}'] = _quad_pnl(GH_TL_V50, aft,
                                            G_BOOST_THRESH_V50, CHAMPION_BOOST_V50)

    # Group C: CHAMPION_BOOST confirm at v50 champion (ghtl=-0.80, aft=0.67)
    for cb in CB_SWEEP_C:
        tc = f'{int(round(cb * 100)):03d}'
        pnl[f'v51_C_cb{tc}'] = _quad_pnl(GH_TL_V50, A_FIRE_THRESH_V50,
                                           G_BOOST_THRESH_V50, cb)

    # Group D: Joint grid — extend GH_TL below -0.80 with aft=0.67
    for gh_tl in GHTL_D:
        for aft in AFT_D:
            for cb in CB_D:
                sign = 'm'
                tl   = f'{abs(int(round(gh_tl * 100))):03d}'
                ta   = f'{int(round(aft * 100)):03d}'
                tc   = f'{int(round(cb * 100)):03d}'
                pnl[f'v51_D_ghtl{sign}{tl}_aft{ta}_cb{tc}'] = _quad_pnl(
                    gh_tl, aft, G_BOOST_THRESH_V50, cb)

    return pnl


# =============================================================================
#  MAIN
# =============================================================================
def main() -> None:
    t_start = time.time()
    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)

    BAR = "=" * 100
    print(BAR)
    print("  CRYPTO BSDT v51 — GH_TL deep-sweep below -0.80 at v50 champion baseline")
    print("  v50 champion: GH_TL=-0.80, G_BOOST_THRESH=0.45, CHAMPION_BOOST=0.60, "
          "A_FIRE_THRESH=0.67")
    print("                Sharpe=+3.7172")
    print("  Key question: does joint GH_TL optimum continue below -0.80 toward -1.00?")
    print(f"  Group A (GH_TL deep @v50 baseline): {GHTL_SWEEP_A}")
    print(f"  Group B (A_FIRE_THRESH fine @ghtl=-0.80): {AFT_SWEEP_B}")
    print(f"  Group C (CHAMPION_BOOST confirm @v50): {CB_SWEEP_C}")
    print(f"  Group D (Joint: GH_TL {GHTL_D} x aft {AFT_D} x cb {CB_D})")
    print(f"  Total variants: {3 + len(GHTL_SWEEP_A) + len(AFT_SWEEP_B) + len(CB_SWEEP_C) + len(GHTL_D)*len(AFT_D)*len(CB_D)}")
    print(BAR)

    def _tstep(msg):
        print(f"\n{msg}", flush=True)

    # -- 1. 1h data -----------------------------------------------------------
    _tstep("[1] Fetching 1h data ... t=0s")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_1h  = df_1h.index >= TEST_START
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    print(f"    Total 1h bars: {len(df_1h):,}  "
          f"train={int(train_1h.sum()):,}  test={int(test_1h.sum()):,}", flush=True)

    # -- 2. Funding rates -----------------------------------------------------
    _tstep(f"[2] Fetching funding rates ... t={time.time()-t_start:.0f}s")
    try:
        funding  = _cached_fetch_binance_funding()
        fund_eth = funding.get('ETHUSDT') if isinstance(funding, dict) else None
        fund_btc = funding.get('BTCUSDT') if isinstance(funding, dict) else None
    except Exception as _e:
        print(f"    Warning: funding fetch failed: {_e}")
        fund_eth = fund_btc = None

    # -- 3. State panel -------------------------------------------------------
    _tstep(f"[3] Building state panel ... t={time.time()-t_start:.0f}s")
    X_panel = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X_panel = np.nan_to_num(X_panel)

    train_idx  = np.where(train_1h)[0]
    calib_idx  = train_idx[-CALIB_BARS:]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[calib_idx] = True
    print(f"    X_panel shape: {X_panel.shape}  calib_bars={calib_mask.sum()}", flush=True)

    # -- 4. Engine + k=1 operator calibration ---------------------------------
    _tstep(f"[4] Calibrating engine ... t={time.time()-t_start:.0f}s")
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(
        X_panel, calib_mask)
    sigma_n  = getattr(stoch, 'sigma_n', 1.0)
    X_normal = X_panel[calib_mask]
    M_k1     = MasterOperator.calibrate(X_normal, k=PCA_K_B)

    # -- 5. v36/v37/v38 signals -----------------------------------------------
    _tstep(f"[5] Computing signals ... t={time.time()-t_start:.0f}s")
    sig_v36           = compute_intraday_signals(X_panel, df_1h, M, net, ews, stoch, e_star, theta)
    sig_v37, _, _     = compute_price_prediction_signals(X_panel, df_1h, M, sig_v36, e_star, sigma_n)
    lam_feat          = compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))

    # -- 6. Four-channel collapse geometry ------------------------------------
    _tstep(f"[6] Four-channel signals ... t={time.time()-t_start:.0f}s")
    mu_norm         = calibrate_channel_means(X_panel, calib_mask, M_k1)
    fire_thresholds = calibrate_firing_thresholds(X_panel, calib_mask, M_k1,
                                                   pct=FIRE_PERCENTILE)
    sig_4ch = compute_four_channel_signals_v39b(
        X_panel, df_1h, M_k1, sig_v36, fire_thresholds, mu_norm)
    print(f"    Done. t={time.time()-t_start:.0f}s", flush=True)

    # -- 7. v34 base portfolio ------------------------------------------------
    _tstep(f"[7] v34 base portfolio ... t={time.time()-t_start:.0f}s")
    h_strats = compute_1h_strategies(df_1h, has_sol)
    df_d     = _cached_fetch_and_prepare()
    df_d     = _cached_add_cross_market(df_d)
    fund_d   = _cached_fetch_binance_funding()
    df_d     = add_leverage_features(df_d, fund_d)
    train_mask_d   = (df_d.index >= TRAIN_START) & (df_d.index <= TRAIN_END)
    train_mask_arr = np.asarray(train_mask_d, dtype=bool)
    pos_dict, _, F_daily, gate_daily = build_daily_positions(
        df_d, train_mask_d, train_mask_arr)
    instr_map = {
        'D1_trend_eth': df_1h['ret_eth'],
        'D2_pairs_eb':  df_1h['spread_ret_eb'],
        'D3_pairs_es':  df_1h['ret_eth'] - df_1h.get('ret_sol', df_1h['ret_eth']),
        'D4_macro_btc': df_1h['ret_btc'],
        'D5_macro_btc': df_1h['ret_btc'],
        'D5_macro_alt': df_1h['ret_eth'],
    }
    d_strats_1h = {
        name: upsample_daily_to_1h_pnl(pos, instr_map.get(name, df_1h['ret_eth']), gate_daily)
        for name, pos in pos_dict.items()
    }
    all_pnls = {**d_strats_1h, **h_strats}
    Q_v34    = compute_quality(all_pnls, bpd=BPD)
    base_pnl = assemble_combined(all_pnls, Q_v34)
    test_mask = base_pnl.index >= TEST_START
    st_v34   = _stats(base_pnl[test_mask])
    print(f"    v34 Sharpe: {st_v34['sharpe']:+.3f}  MaxDD: {st_v34['max_dd']:+.1%}  "
          f"CAGR: {st_v34['cagr']:+.1%}", flush=True)

    # -- 8. Compute all v51 sizing variants -----------------------------------
    print("\n[8] Computing v51 sizing variants ...")
    pnl_variants = apply_v51_sizing(base_pnl, sig_v36, lam_feat, sig_4ch)
    print(f"    {len(pnl_variants)} variants computed.")

    # -- 9. Evaluate all variants ---------------------------------------------
    print("\n[9] Evaluating on test period ...")
    rows: list[dict] = []
    for name, ts in pnl_variants.items():
        st   = _stats(ts[test_mask])
        win  = float((ts[test_mask].fillna(0.0) > 0).mean() * 100)
        days = int(test_mask.sum() / 24)
        rows.append(dict(name=name,
                         sharpe=st['sharpe'], maxdd=float(st['max_dd']) * 100,
                         cagr=float(st['cagr']) * 100, win=win, days=days,
                         final=float(st['final'])))

    df_res = pd.DataFrame(rows).sort_values('sharpe', ascending=False)

    # -- 10. Print gross snapshot ---------------------------------------------
    print(f"\n{'='*100}")
    print(f"  GROSS SNAPSHOT  (test bars={int(test_mask.sum()):,})")
    print(f"{'='*100}")
    print(f"  {'Strategy':<62} {'Sharpe':>7} {'MaxDD':>8} {'CAGR':>10} "
          f"{'Win%':>7} {'Days':>6} {'$100->':>10}")
    print(f"  {'-'*62} {'-'*7} {'-'*8} {'-'*10} {'-'*7} {'-'*6} {'-'*10}")
    for r in df_res.itertuples():
        print(f"  {r.name:<62} {r.sharpe:>+7.3f}   {r.maxdd:>+6.1f}%   {r.cagr:>+8.1f}%"
              f"   {r.win:>6.1f}%  {r.days:>4}d  ${r.final:>8.2f}")

    # -- 11. Group summaries --------------------------------------------------
    print(f"\n{'='*100}")
    print("  PER-GROUP SUMMARIES")
    print(f"{'='*100}")

    groups = {
        'A (GH_TL deep @v50 baseline)':      [r for r in df_res.itertuples() if '_A_' in r.name],
        'B (A_FIRE_THRESH @ghtl=-0.80)':      [r for r in df_res.itertuples() if '_B_' in r.name],
        'C (CHAMPION_BOOST @v50 baseline)':   [r for r in df_res.itertuples() if '_C_' in r.name],
        'D (Joint GH_TL x AFT x CB)':        [r for r in df_res.itertuples() if '_D_' in r.name],
        'Refs':                               [r for r in df_res.itertuples() if '_ref' in r.name],
    }

    for gname, gresp in groups.items():
        if not gresp:
            continue
        best = gresp[0]
        print(f"\n  Group {gname}:")
        print(f"    Best: {best.name}")
        print(f"    Sharpe={best.sharpe:+.4f}  MaxDD={best.maxdd:+.1f}%  "
              f"CAGR={best.cagr:+.1f}%")
        for r in gresp:
            print(f"      {r.name:<66} {r.sharpe:>+7.4f}  MaxDD={r.maxdd:>+6.1f}%")

    # -- 12. Overall best -----------------------------------------------------
    best_row  = df_res.iloc[0]
    best_name = str(best_row['name'])
    v50_ref_mask = df_res['name'] == 'v50_champion_ref'
    v50_ref   = df_res[v50_ref_mask].iloc[0] if v50_ref_mask.any() else None
    improvement = float(best_row['sharpe']) - (float(v50_ref['sharpe']) if v50_ref is not None else 3.7172)

    print(f"\n{'='*100}")
    print(f"  *** OVERALL BEST v51: {best_name}")
    print(f"      Sharpe={best_row['sharpe']:+.4f}  MaxDD={best_row['maxdd']:+.1f}%  "
          f"CAGR={best_row['cagr']:+.1f}%")
    print(f"      v50 champion ref: Sharpe=+3.7172")
    if v50_ref is not None:
        print(f"      v50 champion (recomputed): Sharpe={v50_ref['sharpe']:+.4f}")
    print(f"      Improvement vs v50: Delta={improvement:+.4f} Sharpe")
    if improvement < 0.005:
        print("      *** MAXIMUM LIKELY REACHED -- improvement < 0.005 ***")
    print(f"{'='*100}")

    # -- 13. Year-on-year tables ----------------------------------------------
    top_names = (
        list(df_res[df_res['name'].str.contains('_ref')]['name'])
        + list(df_res[~df_res['name'].str.contains('_ref')].head(5)['name'])
    )
    print(f"\n{'='*100}")
    print("  YEAR-ON-YEAR  ($100 start, compounding, gross)")
    print(f"{'='*100}")
    for name in top_names:
        _yoy_table(name, pnl_variants[name])

    # -- 14. Save results -----------------------------------------------------
    out_json = OUT_DIR_ / 'crypto_bsdt_v51_ghtl_deep.json'

    def _to_py(v):
        if isinstance(v, (np.integer,)): return int(v)
        if isinstance(v, (np.floating,)): return float(v)
        return v

    records = [{k: _to_py(vv) for k, vv in r.items()} for r in df_res.to_dict(orient='records')]
    with open(out_json, 'w') as f:
        json.dump({'champion': best_name,
                   'improvement_vs_v50': float(improvement),
                   'v50_sharpe': 3.7172,
                   'results': records}, f, indent=2)
    print(f"\n  Results saved -> {out_json}")
    print(f"  Total elapsed: {time.time() - t_start:.1f}s")
    print(BAR)


if __name__ == '__main__':
    main()
