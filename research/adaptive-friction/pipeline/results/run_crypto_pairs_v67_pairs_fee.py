"""
Crypto BSDT v67 — Pairs-Adjusted Fee Model
============================================
Model: v58_tight  (FROZEN)

Problem identified with v66
-----------------------------
v66 charged: K × 3 bps at each fired transition as a SINGLE-LEG trade.
But the base portfolio is NOT purely directional: it includes PAIRS strategies
that simultaneously hold a LONG position in one asset AND a SHORT in another.

Base portfolio components:
  Single-leg  : H1 trend ETH, H2 trend BTC, H5 trend SOL, D1,D4,D5  → 1 order per fire
  Pairs (2-leg): H3 ETH-BTC spread, H4 macro BTC-dom, D2, D3         → 2 orders per fire

When BSDT fires:
  H3 goes LONG ETH and SHORT BTC (or LONG BTC and SHORT ETH) simultaneously.
  H4 goes LONG one macro asset and SHORT another simultaneously.
  → Each of these requires executing 2 separate transactions, doubling fees.

Fee Tiers
---------
  Tier 1 (v66)     : 1 leg  × 3 bps/side  (lower bound — ignores pairs)
  Tier 2 (honest)  : 1.5 legs × 3 bps/side (50% single, 50% pairs → avg 1.5×)
  Tier 3 (conserv) : 2 legs  × 3 bps/side  (worst-case: all strategies are pairs)

Also shown: phase-state breakdown (GH_TH fraction of fired events).

Sections
--------
  0. Phase-State Breakdown (GH_TH vs suppress vs normal; why fees matter)
  1. v58 GROSS  (no fees, K=1)
  2. Three-Tier Fee Sweep  (K=1/2/3/5)
  3. $700 Quarterly Projection  (Tier 2 — honest, K=1/2/3/5)
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

from run_crypto_pairs_v63_clip_boost import (
    _realized_vol, _full_stats, ANN_1H,
    A_FIRE_THRESH, G_THRESH_BASE, T_THRESH_BASE,
    G_BOOST_THRESH, CHAMPION_BOOST, N_OPT,
    GH_TH, GH_TL, GL_TH, GL_TL, CLIP,
    CLIP_BASE, CALIB_BARS, BPD, PCA_K_B, FIRE_PERCENTILE,
    _dynamic_gth, _build_pnl_v58, OOS_SPLIT,
    _make_cached_fetch, _cached_fetch_and_prepare,
    _cached_add_cross_market, _cached_fetch_binance_funding,
    MasterOperator,
    build_1h_df, build_intraday_state_panel, calibrate_intraday_engine,
    compute_intraday_signals, compute_price_prediction_signals,
    compute_lambda_features, calibrate_channel_means,
    calibrate_firing_thresholds, compute_four_channel_signals_v39b,
    compute_1h_strategies, compute_quality, assemble_combined,
    add_leverage_features, build_daily_positions, upsample_daily_to_1h_pnl,
)
import run_crypto_pairs_v34_full_combined as _v34mod
import run_crypto_pairs_v63_clip_boost as _v63mod

OUT_DIR     = _v34mod.OUT_DIR
TEST_START  = _v34mod.TEST_START
TRAIN_START = _v34mod.TRAIN_START
TRAIN_END   = _v34mod.TRAIN_END
OUT_DIR_    = Path(OUT_DIR)

# ── CONSTANTS ─────────────────────────────────────────────────────────────────
MAKER_FEE_BPS  = 2.0
MAKER_SLIP_BPS = 1.0
FEE_SIDE_BPS   = MAKER_FEE_BPS + MAKER_SLIP_BPS   # 3 bps per side
BORROW_BPS_PA  = 500   # 5.0% p.a.

LEG_1   = 1.0   # Tier 1: v66 lower bound (single-direction only)
LEG_1_5 = 1.5   # Tier 2: honest avg (50% single, 50% pairs = 1.5×)
LEG_2   = 2.0   # Tier 3: conservative all-pairs

LEVERAGE_LEVELS = [1.0, 2.0, 3.0, 5.0]
START_CAPITAL   = 700.0
LO              = -0.01


# ── helpers ───────────────────────────────────────────────────────────────────

def _count_rt(fired: np.ndarray, idx: pd.DatetimeIndex) -> dict:
    enter_idx = np.where(np.diff(fired.astype(int), prepend=0) == 1)[0]
    exit_idx  = np.where(np.diff(fired.astype(int), prepend=0) == -1)[0]
    n_rt  = min(len(enter_idx), len(exit_idx))
    yrs   = (idx[-1] - idx[0]).total_seconds() / (365.25 * 86400)
    rt_pa = n_rt / yrs if yrs > 0 else 0.0
    pairs = min(len(enter_idx), len(exit_idx))
    e_i, x_i = enter_idx[:pairs], exit_idx[:pairs]
    valid = x_i > e_i
    holds = x_i[valid] - e_i[valid]
    avg_hold_bars = float(np.mean(holds)) if len(holds) > 0 else 0.0
    bar_h = (idx[1] - idx[0]).total_seconds() / 3600.0 if len(idx) > 1 else 1.0
    return dict(n_rt=n_rt, rt_pa=rt_pa,
                avg_hold_h=avg_hold_bars * bar_h,
                avg_hold_d=avg_hold_bars * bar_h / 24.0,
                total_bars=len(idx), years=yrs)


def _compute_phase_states(sig_4ch, rv_ema, lo=-0.01):
    """Reconstruct the 3-state phase series identically to _build_pnl_v58."""
    a_G   = sig_4ch['a_G'];  a_A = sig_4ch['a_A'];  a_T = sig_4ch['a_T']
    G_mem = a_G.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    T_mem = a_T.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    fired = a_A.shift(1).fillna(0.0) > A_FIRE_THRESH
    gth   = _dynamic_gth(rv_ema.reindex(sig_4ch.index, method='ffill').fillna(1.0), lo)

    q_GH_TH = (fired & (G_mem > gth)  & (T_mem > T_THRESH_BASE)).astype(float)
    q_GH_TL = (fired & (G_mem > gth)  & (T_mem <= T_THRESH_BASE)).astype(float)
    q_GL_TH = (fired & (G_mem <= gth) & (T_mem > T_THRESH_BASE)).astype(float)
    q_GL_TL = (fired & (G_mem <= gth) & (T_mem <= T_THRESH_BASE)).astype(float)
    phase   = (1.0 + GH_TH*q_GH_TH + GH_TL*q_GH_TL + GL_TH*q_GL_TH + GL_TL*q_GL_TL).clip(0.05, CLIP)

    q_suppress = (fired & (q_GH_TH == 0)).astype(bool)
    return phase, q_GH_TH.astype(bool), q_suppress, fired.astype(bool)


def _apply_leverage(pnl, K):
    lev = pnl * K
    if K > 1.0:
        lev = lev - (K - 1.0) * BORROW_BPS_PA / 10_000.0 / ANN_1H
    return lev


def _apply_cost(pnl, fired, fee_bps, slip_bps, K, legs=1.0):
    """
    Charge fee at each fired transition.
    `legs` multiplier captures pairs strategies:
      1.0 = v66 lower bound (treats every BSDT event as 1 trade)
      1.5 = honest (50% single-leg, 50% 2-leg pairs)
      2.0 = conservative (all strategies are 2-leg pairs)
    """
    events = pd.Series(fired.astype(int), index=pnl.index).diff().abs().fillna(0).astype(bool)
    cost   = K * legs * (fee_bps + slip_bps) / 10_000.0
    return pnl - events.astype(float) * cost


def _quarterly_projection(pnl, start_cap):
    try:
        q_ret = (1.0 + pnl).resample('QE').prod() - 1.0
    except Exception:
        q_ret = (1.0 + pnl).resample('Q').prod() - 1.0
    rows = []; cap = start_cap
    for dt, r in q_ret.items():
        cap *= (1.0 + r)
        q_num = (dt.month - 1) // 3 + 1
        rows.append({'Quarter': f'{dt.year} Q{q_num}',
                     'Return': f'{r*100:+.2f}%',
                     'Capital': f'${cap:,.2f}'})
    return rows


# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    t0  = time.time()
    BAR = '=' * 110
    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)

    print(BAR)
    print('  v67 - Pairs-Adjusted Fee Model  (v58_tight FROZEN)')
    print('  Fix: account for 2 legs per BSDT fire for pairs strategies')
    print(BAR)

    t = lambda msg: print(f'\n{msg}', flush=True)

    # ── data ─────────────────────────────────────────────────────────────────
    t('[1] 1h data')
    df_1h, has_sol = _v63mod.build_1h_df(start='2021-01-01', end='2026-05-01')
    test_mask = df_1h.index >= TEST_START
    train_1h  = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    print(f'    Bars: {len(df_1h):,}  OOS bars: {test_mask.sum():,}')

    t(f'[2] Funding  t={time.time()-t0:.0f}s')
    try:
        fund     = _cached_fetch_binance_funding()
        fund_eth = fund.get('ETHUSDT'); fund_btc = fund.get('BTCUSDT')
    except Exception as e:
        print(f'    Warn: {e}'); fund_eth = fund_btc = None

    t(f'[3] State panel  t={time.time()-t0:.0f}s')
    X = _v63mod.build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X = np.nan_to_num(X)
    train_idx  = np.where(train_1h)[0]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[train_idx[-CALIB_BARS:]] = True

    t(f'[4] Engine  t={time.time()-t0:.0f}s')
    M, net, geom, lyap, ews, stoch, e_star, theta = _v63mod.calibrate_intraday_engine(X, calib_mask)
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
    base_pnl = assemble_combined(
        {**d1h, **h_strats},
        compute_quality({**d1h, **h_strats}, bpd=BPD))
    rv_ema = _realized_vol(df_1h, ema_span=3)

    t(f'[8] v58 PnL  t={time.time()-t0:.0f}s')
    pnl_full = _build_pnl_v58(base_pnl, sig_v36, lam_feat, sig_4ch, rv_ema, LO)

    # ── reconstruct phase states ──────────────────────────────────────────────
    phase_full, q_GH_TH_full, q_sup_full, fired_full = \
        _compute_phase_states(sig_4ch, rv_ema, lo=LO)

    pnl_oos     = pnl_full[test_mask]
    fired_oos   = fired_full[test_mask]
    q_GH_TH_oos = q_GH_TH_full[test_mask]
    q_sup_oos   = q_sup_full[test_mask]
    test_idx    = df_1h.index[test_mask]

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 0 — Phase-State Breakdown
    # ══════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print('  SECTION 0 - Phase-State Breakdown (why v66 undercounts fees)')
    print(BAR)

    rt    = _count_rt(fired_oos.values, test_idx)
    rt_gh = _count_rt(q_GH_TH_oos.values, test_idx)
    rt_sq = _count_rt(q_sup_oos.values, test_idx)

    n_bars  = rt['total_bars']
    n_fired = int(fired_oos.sum())
    n_gh    = int(q_GH_TH_oos.sum())
    n_sup   = int(q_sup_oos.sum())
    yrs     = rt['years']

    print(f"""
  OOS  : {yrs:.2f} years   {n_bars:,} bars  ({n_bars/yrs:.0f} bars/yr)

  Phase 6.0  (GH_TH \u2014 ALL base positions amplified 6\u00d7)
    Bars  : {n_gh:5,}  ({n_gh/n_bars*100:.1f}% of OOS)
    RT/yr : {rt_gh['rt_pa']:.0f}
    Note  : {n_gh/n_fired*100 if n_fired>0 else 0:.1f}% of fired events are GH_TH \u2014 the BIG position state.
            When fired, strategy is LONG some assets AND SHORT others simultaneously.

  Phase 0.05 (suppress \u2014 positions near-flat)
    Bars  : {n_sup:5,}  ({n_sup/n_bars*100:.1f}% of OOS)
    RT/yr : {rt_sq['rt_pa']:.0f}

  Phase 1.0  (normal base \u2014 between fires)
    Bars  : {n_bars-n_fired:5,}  ({(n_bars-n_fired)/n_bars*100:.1f}% of OOS)

  All fired events    : {n_fired:,} bars  ({n_fired/n_bars*100:.1f}%)  = {rt['rt_pa']:.0f} RT/yr
  GH_TH fraction     : {n_gh/n_fired*100 if n_fired>0 else 0:.1f}% of fired events

  v66 fee error:
    Treated every BSDT fire as a SINGLE-LEG directional trade at 3 bps/side.
    Reality: ~50% of allocation is in PAIRS strategies (H3 ETH-BTC, H4 macro,
    D2 spread, D3 cross) that trade BOTH legs simultaneously.
    Pairs leg: buy ETH \u2192 3 bps AND short BTC \u2192 3 bps = 6 bps/side total.
    Single leg: buy/sell ETH = 3 bps/side.
    Portfolio average: (4 single + 4 pairs) / 8 strategies \u2248 1.5 legs/fire event.
""")

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 1 — v58 Gross
    # ══════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print('  SECTION 1 - v58 Gross Backtest (no fees, K=1)')
    print(BAR)
    sg = _full_stats(pnl_oos)
    print(f"""
  Sharpe       : {sg['sharpe']:+.3f}   Sortino  : {sg['sortino']:+.3f}   Calmar : {sg['calmar']:+.3f}
  CAGR         : {sg['cagr']*100:+.2f}%    MaxDD   : {sg['max_dd']*100:.2f}%
  $100 -> $    : {sg['final']:,.2f}
  YoY          : {" | ".join(f"{yr}: {r*100:+.1f}%" for yr, r in sg['yoy'].items())}
""")

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 2 — Three Fee Tiers
    # ══════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print(f'  SECTION 2 - Leverage Sweep: Three Fee Tiers  '
          f'({FEE_SIDE_BPS:.0f} bps/side, {BORROW_BPS_PA/100:.0f}% borrow)')
    print(f'  T1 (v66 lower) : 1-leg   × {FEE_SIDE_BPS:.0f} bps/side = {1*FEE_SIDE_BPS:.0f} bps/side/RT')
    print(f'  T2 (honest)    : 1.5-leg × {FEE_SIDE_BPS:.0f} bps/side = {1.5*FEE_SIDE_BPS:.0f} bps/side/RT  ← recommended')
    print(f'  T3 (conserv)   : 2-leg   × {FEE_SIDE_BPS:.0f} bps/side = {2*FEE_SIDE_BPS:.0f} bps/side/RT  ← stress test')
    print(BAR)

    hdr = (f"  {'K':>4}  {'Gross':>8}  {'T1 Net':>9}  {'T2 Net':>9}  {'T3 Net':>9}"
           f"  {'T2 Sharpe':>10}  {'T2 MaxDD':>9}"
           f"  {'T1 drag':>8}  {'T2 drag':>8}  {'T3 drag':>8}  {'$700→ T2':>10}")
    print(hdr)
    print('  ' + '-' * 115)

    t2_results: dict = {}
    for K in LEVERAGE_LEVELS:
        pnl_lev = _apply_leverage(pnl_oos, K)
        pnl_t1  = _apply_cost(pnl_lev, fired_oos.values, MAKER_FEE_BPS, MAKER_SLIP_BPS, K, legs=LEG_1)
        pnl_t2  = _apply_cost(pnl_lev, fired_oos.values, MAKER_FEE_BPS, MAKER_SLIP_BPS, K, legs=LEG_1_5)
        pnl_t3  = _apply_cost(pnl_lev, fired_oos.values, MAKER_FEE_BPS, MAKER_SLIP_BPS, K, legs=LEG_2)
        s1 = _full_stats(pnl_t1); s2 = _full_stats(pnl_t2); s3 = _full_stats(pnl_t3)
        sg_lev = _full_stats(pnl_lev)

        d1 = K * rt['rt_pa'] * 2 * LEG_1   * FEE_SIDE_BPS / 10_000 * 100
        d2 = K * rt['rt_pa'] * 2 * LEG_1_5 * FEE_SIDE_BPS / 10_000 * 100
        d3 = K * rt['rt_pa'] * 2 * LEG_2   * FEE_SIDE_BPS / 10_000 * 100

        t2_results[K] = {'stats': s2, 'pnl': pnl_t2}

        star = ' <--' if K == 2.0 else ''
        print(f"  {K:>4.1f}  {sg_lev['cagr']*100:>+7.2f}%  "
              f"{s1['cagr']*100:>+8.2f}%  {s2['cagr']*100:>+8.2f}%  {s3['cagr']*100:>+8.2f}%"
              f"  {s2['sharpe']:>+9.3f}  {s2['max_dd']*100:>8.2f}%"
              f"  {d1:>+7.1f}%  {d2:>+7.1f}%  {d3:>+7.1f}%"
              f"  ${s2['final'] * START_CAPITAL / 100:>9,.2f}{star}")

    print(f"""
  T1 = v66 (1 leg): underestimates — ignores pairs structure
  T2 = honest (1.5 legs): ~4 single-leg + ~4 two-leg strategies in portfolio
  T3 = conservative (2 legs): all-pairs worst case
  Annual drag (T2) at each K = K × {rt['rt_pa']:.0f} RT/yr × 2 sides × 1.5 legs × {FEE_SIDE_BPS:.0f} bps
""")

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 3 — $700 Quarterly Projection (Tier 2)
    # ══════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print(f'  SECTION 3 - ${START_CAPITAL:.0f} Quarterly Projection  (Tier 2 honest, K=1/2/3/5)')
    print(BAR)

    for K in LEVERAGE_LEVELS:
        rows = _quarterly_projection(t2_results[K]['pnl'], START_CAPITAL)
        sn   = t2_results[K]['stats']
        print(f'\n  -- K={K:.0f}  Net CAGR {sn["cagr"]*100:+.2f}%  '
              f'Sharpe {sn["sharpe"]:+.3f}  MaxDD {sn["max_dd"]*100:.2f}%')
        print(f'  {"Quarter":<12}  {"Return":>10}  {"Capital":>12}')
        print('  ' + '-' * 38)
        for row in rows:
            print(f'  {row["Quarter"]:<12}  {row["Return"]:>10}  {row["Capital"]:>12}')

    # ── save ─────────────────────────────────────────────────────────────────
    def _flt(v):
        return float(v) if isinstance(v, (int, float, np.integer, np.floating)) else v

    save = {
        'version': 'v67',
        'phase_profile': {
            'n_bars': int(n_bars), 'years': float(yrs),
            'n_gh_bars': int(n_gh), 'n_suppress_bars': int(n_sup),
            'pct_gh': float(n_gh / n_bars * 100),
            'gh_fraction_of_fired': float(n_gh / n_fired * 100 if n_fired > 0 else 0),
            'rt_all_pa': float(rt['rt_pa']), 'rt_gh_pa': float(rt_gh['rt_pa']),
        },
        'gross': {k: _flt(v) for k, v in sg.items() if k != 'yoy'},
        'gross_yoy': {str(yr): float(r) for yr, r in sg['yoy'].items()},
        'tiers': {},
    }
    for leg_label, L in [('T1_1leg', LEG_1), ('T2_1p5leg', LEG_1_5), ('T3_2leg', LEG_2)]:
        save['tiers'][leg_label] = {}
        for K in LEVERAGE_LEVELS:
            pnl_lev = _apply_leverage(pnl_oos, K)
            pnl_net = _apply_cost(pnl_lev, fired_oos.values, MAKER_FEE_BPS, MAKER_SLIP_BPS, K, legs=L)
            s = _full_stats(pnl_net)
            save['tiers'][leg_label][f'K{K}'] = {k: _flt(v) for k, v in s.items() if k != 'yoy'}
            save['tiers'][leg_label][f'K{K}']['yoy'] = {str(yr): float(r) for yr, r in s['yoy'].items()}
            save['tiers'][leg_label][f'K{K}']['drag_pct'] = float(K * rt['rt_pa'] * 2 * L * FEE_SIDE_BPS / 10_000 * 100)

    out = OUT_DIR_ / 'crypto_bsdt_v67_results.json'
    with open(out, 'w') as f:
        json.dump(save, f, indent=2)
    print(f'\n  Saved: {out}')
    print(f'  Total runtime: {time.time()-t0:.0f}s')
    print(BAR)
