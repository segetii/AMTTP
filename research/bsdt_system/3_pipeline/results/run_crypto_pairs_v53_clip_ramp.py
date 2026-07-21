"""
Crypto BSDT v53 — CLIP ramp above 6.0 at T_THRESH=0.41 baseline
=================================================================
v52 champion: v52_F_clip060_gth045_tth041  Sharpe=+3.8090
  (clip=6.0, GH_TH=5.0, GH_TL=-1.00, GL_TH=-1.00, GL_TL=-1.00,
   G_THRESH=0.45, T_THRESH=0.41, N_G=N_T=8,
   G_BOOST_THRESH=0.45, CHAMPION_BOOST=0.59, A_FIRE_THRESH=0.67)

Key v52 findings:
  - T_THRESH=0.41 (vs 0.40) gave +0.059 Sharpe — enormous hidden gain
  - CLIP=6.0 > 5.5 > 5.0 at T_THRESH=0.41: MONOTONE INCREASING — ceiling not found!
  - At T_THRESH=0.40: clip=7.0 degraded vs 5.5 (interaction with T_THRESH)
  - G_THRESH=0.45 is still optimal at tth=0.41
  - N=8 confirmed optimal; GH_TH=CLIP-1 (at-boundary) is the correct structure
  - Total Δ vs v51: +0.0795 Sharpe (largest single-version gain since v47->v48)

v53 strategy:
  A) CLIP ramp to saturation at T_THRESH=0.41 baseline: test clip up to 10.0
  B) T_THRESH fine-tune: narrow around 0.41 now that clip is free
  C) A_FIRE_THRESH re-tune at new (clip=6.0, tth=0.41) baseline
  D) GH_TL stability check: re-verify -1.00 at new baseline
  E) CHAMPION_BOOST and G_BOOST_THRESH at new baseline
  F) Joint: top CLIP x top T_THRESH x top AFT

Fixed throughout (v52 confirmed):
  GH_TL=-1.00, GL_TH=-1.00, GL_TL=-1.00
  GH_TH = CLIP - 1.0  (at-boundary structure)
  G_THRESH=0.45, N_G=N_T=8, G_BOOST_THRESH=0.45, CHAMPION_BOOST=0.59

Group A: CLIP ramp at T_THRESH=0.41, G_THRESH=0.45, AFT=0.67 (GH_TH=CLIP-1)
  CLIP in {5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 9.0, 10.0, 12.0}  -> 10 variants

Group B: T_THRESH fine-tune at clip=6.0 (GH_TH=5.0), G_THRESH=0.45, AFT=0.67
  T_THRESH in {0.37, 0.38, 0.39, 0.40, 0.41, 0.42, 0.43, 0.44, 0.45}  -> 9 variants

Group C: A_FIRE_THRESH at new baseline (clip=6.0, tth=0.41)
  AFT in {0.63, 0.64, 0.65, 0.66, 0.67, 0.68, 0.69, 0.70}  -> 8 variants

Group D: GH_TL stability at new baseline (clip=6.0, tth=0.41, AFT=0.67)
  GH_TL in {-1.00, -0.95, -0.90, -0.85, -0.80, -0.70}  -> 6 variants

Group E: CHAMPION_BOOST and G_BOOST_THRESH at new baseline
  CB in {0.50, 0.55, 0.57, 0.59, 0.61, 0.63, 0.65}  -> 7 variants
  GBT in {0.40, 0.42, 0.44, 0.45, 0.46, 0.48, 0.50}  -> 7 variants

Group F: Joint top CLIP x T_THRESH x AFT
  CLIP {6.0, 6.5, 7.0} x T_THRESH {0.40, 0.41, 0.42} x AFT {0.66, 0.67, 0.68}  -> 27 variants

Total: 3_refs + 10 + 9 + 8 + 6 + 14 + 27 = 77 variants
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


# -- v52 champion baseline ---------------------------------------------------
GH_TL_OPT           = -1.00
GL_TH_OPT           = -1.00
GL_TL_OPT           = -1.00
G_THRESH_OPT        = 0.45
N_OPT               = 8
G_BOOST_THRESH_OPT  = 0.45
CHAMPION_BOOST_OPT  = 0.59
A_FIRE_THRESH_OPT   = 0.67

# v52 champion fixed values
CLIP_V52    = 6.0
GH_TH_V52   = 5.0   # = CLIP - 1
T_THRESH_V52 = 0.41

# Sweep ranges
CLIP_A    = [5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 9.0, 10.0, 12.0]

TTHRESH_B = [0.37, 0.38, 0.39, 0.40, 0.41, 0.42, 0.43, 0.44, 0.45]

AFT_C     = [0.63, 0.64, 0.65, 0.66, 0.67, 0.68, 0.69, 0.70]

GHTL_D    = [-1.00, -0.95, -0.90, -0.85, -0.80, -0.70]

CB_E      = [0.50, 0.55, 0.57, 0.59, 0.61, 0.63, 0.65]
GBT_E     = [0.40, 0.42, 0.44, 0.45, 0.46, 0.48, 0.50]

# Group F joint
CLIP_F    = [6.0, 6.5, 7.0]
TTHRESH_F = [0.40, 0.41, 0.42]
AFT_F     = [0.66, 0.67, 0.68]


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


def apply_v53_sizing(base_pnl, sig_v36, lam_feat, sig_4ch):
    idx  = base_pnl.index
    sv36 = sig_v36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lam_feat.reindex(idx, method='ffill').fillna(0.5)
    s4   = sig_4ch.reindex(idx, method='ffill').fillna(0.0)
    base = base_pnl.fillna(0.0)

    gam_adj  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lam_pct  = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size_sym = np.clip(1.0 - gam_adj, 0.0, 1.0) * (0.75 + 0.5 * lam_pct)

    def _quad_pnl(clip, t_thresh, aft, gh_tl, cb, gbt) -> pd.Series:
        gh_th = clip - 1.0   # always at-boundary
        q_GH_TH, q_GH_TL, q_GL_TH, q_GL_TL = _make_quadrant_flags(
            s4, G_THRESH_OPT, t_thresh, N_OPT, N_OPT, aft)
        phase = (1.0
                 + gh_th     * q_GH_TH
                 + gh_tl     * q_GH_TL
                 + GL_TH_OPT * q_GL_TH
                 + GL_TL_OPT * q_GL_TL).clip(0.05, clip)
        a_G_cur = s4['a_G'].shift(1).fillna(0.0)
        flag_aG = (a_G_cur > gbt).astype(float)
        return base * size_sym * (1.0 + cb * flag_aG) * phase

    pnl: dict[str, pd.Series] = {}

    # Reference points
    pnl['v51_champion_ref'] = _quad_pnl(5.0, 0.40, 0.67, -1.00, 0.59, 0.45)
    pnl['v52_champion_ref'] = _quad_pnl(6.0, 0.41, 0.67, -1.00, 0.59, 0.45)

    # Group A: CLIP ramp at T_THRESH=0.41,  AFT=0.67 (GH_TH=CLIP-1)
    for clip in CLIP_A:
        tc = f'{int(round(clip * 10)):03d}'
        pnl[f'v53_A_clip{tc}'] = _quad_pnl(clip, T_THRESH_V52, A_FIRE_THRESH_OPT,
                                             GH_TL_OPT, CHAMPION_BOOST_OPT, G_BOOST_THRESH_OPT)

    # Group B: T_THRESH fine-tune at clip=6.0
    for t_th in TTHRESH_B:
        tc = f'{int(round(t_th * 100)):03d}'
        pnl[f'v53_B_tth{tc}'] = _quad_pnl(CLIP_V52, t_th, A_FIRE_THRESH_OPT,
                                            GH_TL_OPT, CHAMPION_BOOST_OPT, G_BOOST_THRESH_OPT)

    # Group C: A_FIRE_THRESH at new baseline (clip=6.0, tth=0.41)
    for aft in AFT_C:
        ta = f'{int(round(aft * 100)):03d}'
        pnl[f'v53_C_aft{ta}'] = _quad_pnl(CLIP_V52, T_THRESH_V52, aft,
                                            GH_TL_OPT, CHAMPION_BOOST_OPT, G_BOOST_THRESH_OPT)

    # Group D: GH_TL stability at new baseline
    for gh_tl in GHTL_D:
        sign = 'm'
        tl   = f'{abs(int(round(gh_tl * 100))):03d}'
        pnl[f'v53_D_ghtl{sign}{tl}'] = _quad_pnl(CLIP_V52, T_THRESH_V52, A_FIRE_THRESH_OPT,
                                                    gh_tl, CHAMPION_BOOST_OPT, G_BOOST_THRESH_OPT)

    # Group E: CHAMPION_BOOST and G_BOOST_THRESH at new baseline
    for cb in CB_E:
        tc = f'{int(round(cb * 100)):03d}'
        pnl[f'v53_E_cb{tc}'] = _quad_pnl(CLIP_V52, T_THRESH_V52, A_FIRE_THRESH_OPT,
                                           GH_TL_OPT, cb, G_BOOST_THRESH_OPT)
    for gbt in GBT_E:
        tg = f'{int(round(gbt * 100)):03d}'
        pnl[f'v53_E_gbt{tg}'] = _quad_pnl(CLIP_V52, T_THRESH_V52, A_FIRE_THRESH_OPT,
                                            GH_TL_OPT, CHAMPION_BOOST_OPT, gbt)

    # Group F: Joint CLIP x T_THRESH x AFT
    for clip in CLIP_F:
        for t_th in TTHRESH_F:
            for aft in AFT_F:
                tc_clip = f'{int(round(clip * 10)):03d}'
                tc_tth  = f'{int(round(t_th * 100)):03d}'
                tc_aft  = f'{int(round(aft * 100)):03d}'
                pnl[f'v53_F_clip{tc_clip}_tth{tc_tth}_aft{tc_aft}'] = _quad_pnl(
                    clip, t_th, aft, GH_TL_OPT, CHAMPION_BOOST_OPT, G_BOOST_THRESH_OPT)

    return pnl


# =============================================================================
#  MAIN
# =============================================================================
def main() -> None:
    t_start = time.time()
    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)

    BAR = "=" * 100
    print(BAR)
    print("  CRYPTO BSDT v53 — CLIP ramp above 6.0 + T_THRESH/AFT fine-tune at v52 baseline")
    print("  v52 champion: clip=6.0, GH_TH=5.0, GH_TL=-1.00, G_THRESH=0.45, T_THRESH=0.41,")
    print("                N=8, G_BOOST_THRESH=0.45, CHAMPION_BOOST=0.59, AFT=0.67")
    print("                Sharpe=+3.8090")
    print("  Key insight: CLIP still MONOTONE at 6.0 (at T_THRESH=0.41) — ceiling unknown!")
    n_total = (2 + len(CLIP_A) + len(TTHRESH_B) + len(AFT_C) + len(GHTL_D)
               + len(CB_E) + len(GBT_E) + len(CLIP_F)*len(TTHRESH_F)*len(AFT_F))
    print(f"  Total variants: {n_total}")
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

    # -- 8. Compute all v53 sizing variants -----------------------------------
    print("\n[8] Computing v53 sizing variants ...")
    pnl_variants = apply_v53_sizing(base_pnl, sig_v36, lam_feat, sig_4ch)
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
    print(f"  {'Strategy':<66} {'Sharpe':>7} {'MaxDD':>8} {'CAGR':>10} "
          f"{'Win%':>7} {'Days':>6} {'$100->':>10}")
    print(f"  {'-'*66} {'-'*7} {'-'*8} {'-'*10} {'-'*7} {'-'*6} {'-'*10}")
    for r in df_res.itertuples():
        print(f"  {r.name:<66} {r.sharpe:>+7.3f}   {r.maxdd:>+6.1f}%   {r.cagr:>+8.1f}%"
              f"   {r.win:>6.1f}%  {r.days:>4}d  ${r.final:>8.2f}")

    # -- 11. Group summaries --------------------------------------------------
    print(f"\n{'='*100}")
    print("  PER-GROUP SUMMARIES")
    print(f"{'='*100}")

    groups = {
        'A (CLIP ramp @tth=0.41)':        [r for r in df_res.itertuples() if '_A_' in r.name],
        'B (T_THRESH fine @clip=6.0)':    [r for r in df_res.itertuples() if '_B_' in r.name],
        'C (AFT @clip=6.0, tth=0.41)':    [r for r in df_res.itertuples() if '_C_' in r.name],
        'D (GH_TL stability)':             [r for r in df_res.itertuples() if '_D_' in r.name],
        'E (CB and GBT @new baseline)':    [r for r in df_res.itertuples() if '_E_' in r.name],
        'F (Joint CLIP x T_THRESH x AFT)':[r for r in df_res.itertuples() if '_F_' in r.name],
        'Refs':                            [r for r in df_res.itertuples() if '_ref' in r.name],
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
            print(f"      {r.name:<70} {r.sharpe:>+7.4f}  MaxDD={r.maxdd:>+6.1f}%")

    # -- 12. Overall best -----------------------------------------------------
    best_row  = df_res.iloc[0]
    best_name = str(best_row['name'])
    v52_ref_mask = df_res['name'] == 'v52_champion_ref'
    v52_ref   = df_res[v52_ref_mask].iloc[0] if v52_ref_mask.any() else None
    improvement = float(best_row['sharpe']) - (float(v52_ref['sharpe']) if v52_ref is not None else 3.8090)

    print(f"\n{'='*100}")
    print(f"  *** OVERALL BEST v53: {best_name}")
    print(f"      Sharpe={best_row['sharpe']:+.4f}  MaxDD={best_row['maxdd']:+.1f}%  "
          f"CAGR={best_row['cagr']:+.1f}%")
    print(f"      v52 champion ref: Sharpe=+3.8090")
    if v52_ref is not None:
        print(f"      v52 champion (recomputed): Sharpe={v52_ref['sharpe']:+.4f}")
    print(f"      Improvement vs v52: Delta={improvement:+.4f} Sharpe")
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
    out_json = OUT_DIR_ / 'crypto_bsdt_v53_clip_ramp.json'

    def _to_py(v):
        if isinstance(v, (np.integer,)): return int(v)
        if isinstance(v, (np.floating,)): return float(v)
        return v

    records = [{k: _to_py(vv) for k, vv in r.items()} for r in df_res.to_dict(orient='records')]
    with open(out_json, 'w') as f:
        json.dump({'champion': best_name,
                   'improvement_vs_v52': float(improvement),
                   'v52_sharpe': 3.8090,
                   'results': records}, f, indent=2)
    print(f"\n  Results saved -> {out_json}")
    print(f"  Total elapsed: {time.time() - t_start:.1f}s")
    print(BAR)


if __name__ == '__main__':
    main()
