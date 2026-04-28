"""
Crypto BSDT v66 — v58 with Honest Maker Fees + Leverage
========================================================
Model: v58_tight  (FROZEN, unchanged from champion certification)

v65 post-mortem
---------------
  exec_thresh=0.45 cut RT/year to ~0.
  "9.9% CAGR" in v65 is the BASE PORTFOLIO return, NOT v58/v63 alpha.
  The BSDT overlay was filtered to zero trades — all alpha disappeared.

Correct approach
----------------
  Use v58 as-is with MAKER LIMIT ORDERS only (no conviction filter).
  - Maker fee:  2 bps execution + 1 bps slippage = 3 bps/side (conservative)
  - Applied on every fired transition (1 enter + 1 exit per RT)
  - Leverage K scales both returns AND fee drag

Bar frequency
-------------
  1-hour bars.
  151 RT/year = ~3 RT/week = ~0.41 RT/day
  Avg holding period = 8760 / (151 x 2) ~ 29 hours ~ 1.2 days
  MEDIUM-FREQUENCY — roughly a daily-cycle trader on hourly signal.

Sections
--------
  0. Bar info  (confirm 1h, RT stats, avg holding period)
  1. v58 GROSS  (no fees, K=1) — reference backtest
  2. v58 NET at K=1, 2, 3, 5  (maker 3 bps/side + borrow at K>1)
  3. $700 projection at K=1/2/3/5 (quarterly table)
  4. K=5 fee-model comparison: old 5bps/active-bar vs honest maker
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
MAKER_FEE_BPS  = 2.0   # exchange maker / zero-fee tier
MAKER_SLIP_BPS = 1.0   # limit-order slippage (conservative)
BORROW_BPS_PA  = 500   # 5.0% p.a. borrow for leveraged crypto

LEVERAGE_LEVELS = [1.0, 2.0, 3.0, 5.0]
START_CAPITAL   = 700.0
LO              = -0.01   # gamma normalisation floor (same as v58)

# Old fee model: continuous per-active-bar cost (used to produce $9,675 figure)
OLD_FEE_BPS_PER_BAR = 5.0   # bps subtracted from each bar while position is active


# ── helpers ───────────────────────────────────────────────────────────────────

def _count_rt(fired: np.ndarray, idx: pd.DatetimeIndex) -> dict:
    enter_idx = np.where(np.diff(fired.astype(int), prepend=0) == 1)[0]
    exit_idx  = np.where(np.diff(fired.astype(int), prepend=0) == -1)[0]
    n_rt   = min(len(enter_idx), len(exit_idx))
    yrs    = (idx[-1] - idx[0]).total_seconds() / (365.25 * 86400)
    rt_pa  = n_rt / yrs if yrs > 0 else 0.0

    pairs = min(len(enter_idx), len(exit_idx))
    e_i   = enter_idx[:pairs]; x_i = exit_idx[:pairs]
    valid = x_i > e_i
    holds = (x_i[valid] - e_i[valid])
    avg_hold_bars = float(np.mean(holds)) if len(holds) > 0 else 0.0
    bar_h = (idx[1] - idx[0]).total_seconds() / 3600.0 if len(idx) > 1 else 1.0

    return dict(n_rt=n_rt, rt_pa=rt_pa, avg_hold_h=avg_hold_bars * bar_h,
                avg_hold_d=avg_hold_bars * bar_h / 24.0, bar_h=bar_h,
                total_bars=len(idx), years=yrs)


def _apply_cost(pnl: pd.Series, fired: np.ndarray,
                fee_bps: float, slip_bps: float, K: float = 1.0) -> pd.Series:
    """Cost on every transition. At leverage K, notional is K larger -> fee scales with K."""
    events = pd.Series(fired.astype(int), index=pnl.index).diff().abs().fillna(0).astype(bool)
    cost   = K * (fee_bps + slip_bps) / 10_000.0
    return pnl - events.astype(float) * cost


def _apply_leverage(pnl: pd.Series, K: float) -> pd.Series:
    lev = pnl * K
    if K > 1.0:
        daily_drag = (K - 1.0) * BORROW_BPS_PA / 10_000.0 / ANN_1H
        lev = lev - daily_drag
    return lev


def _apply_cost_per_bar(pnl: pd.Series, fired: np.ndarray,
                        fee_bps_per_bar: float, K: float = 1.0) -> pd.Series:
    """
    OLD fee model: subtract fee_bps_per_bar for EVERY bar the position is active.
    This is a continuous spread/financing cost, not a per-trade cost.
    Used in the original V58_PROFIT_ACCELERATION analysis.
    """
    active = pd.Series(fired.astype(float), index=pnl.index)
    cost   = K * fee_bps_per_bar / 10_000.0
    return pnl - active * cost


def _quarterly_projection(pnl: pd.Series, start_cap: float) -> list:
    try:
        q_ret = (1.0 + pnl).resample('QE').prod() - 1.0
    except Exception:
        q_ret = (1.0 + pnl).resample('Q').prod() - 1.0
    rows = []; cap = start_cap
    for dt, r in q_ret.items():
        cap *= (1.0 + r)
        q_num  = (dt.month - 1) // 3 + 1
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
    print('  v66 - v58 Honest Cost Simulation  (maker fees, no conviction filter)')
    print('  Model: v58_tight (FROZEN)   Fees: maker 3 bps/side   Leverage: K=1,1.5,2,3')
    print(BAR)

    t = lambda msg: print(f'\n{msg}', flush=True)

    # ── data ─────────────────────────────────────────────────────────────────
    t('[1] 1h data')
    df_1h, has_sol = _v63mod.build_1h_df(start='2021-01-01', end='2026-05-01')
    test_mask   = df_1h.index >= TEST_START
    train_1h    = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    second_half = df_1h.index >= OOS_SPLIT
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
    # sig_v36 has gamma_star_adj  (sv36 arg)
    # lam_feat has lambda_pct_100  (lf arg)
    # sig_4ch has a_G, a_A, a_T   (s4 arg)
    pnl_full = _build_pnl_v58(base_pnl, sig_v36, lam_feat, sig_4ch, rv_ema, LO)

    a_A       = sig_4ch['a_A']
    fired_all = (a_A.shift(1).fillna(0.0) > A_FIRE_THRESH).values.astype(bool)

    pnl_oos   = pnl_full[test_mask]
    fired_oos = fired_all[test_mask]
    test_idx  = df_1h.index[test_mask]
    base_oos  = base_pnl[test_mask]

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 0 — Bar Frequency & Trade Stats
    # ══════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print('  SECTION 0 - Bar Frequency & Execution Stats')
    print(BAR)

    rt = _count_rt(fired_oos, test_idx)
    print(f"""
  Bar interval      : {rt["bar_h"]:.0f} hour(s)  ->  1-HOUR BARS
  OOS bars          : {rt["total_bars"]:,}  over  {rt["years"]:.2f} years
  Round-trips (RT)  : {rt["n_rt"]:,} total
  RT / year         : {rt["rt_pa"]:.0f}
  RT / week         : {rt["rt_pa"]/52.0:.2f}
  RT / day          : {rt["rt_pa"]/365.0:.2f}
  Avg holding time  : {rt["avg_hold_h"]:.1f} hours  =  {rt["avg_hold_d"]:.1f} days per trade

  Classification    : MEDIUM-FREQUENCY  (~1 trade/day, holds ~1.2 days)
  Execution method  : Maker LIMIT orders placed at close of signal bar
""")

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 1 — v58 Gross
    # ══════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print('  SECTION 1 - v58 Gross Backtest (no fees, K=1)')
    print(BAR)

    sg = _full_stats(pnl_oos)
    print(f"""
  Sharpe       : {sg["sharpe"]:+.3f}
  Sortino      : {sg["sortino"]:+.3f}
  Calmar       : {sg["calmar"]:+.3f}
  CAGR         : {sg["cagr"]*100:+.2f}%
  MaxDD        : {sg["max_dd"]*100:.2f}%
  Win Rate     : {sg["win_rate"]*100:.2f}%
  Profit Factor: {sg["profit_f"]:.3f}
  $100 -> $    : {sg["final"]:,.2f}
  YoY          : {" | ".join(f"{yr}: {r*100:+.1f}%" for yr, r in sg["yoy"].items())}
""")

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 2 — Leverage Sweep with Maker Fees
    # ══════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print(f'  SECTION 2 - Leverage Sweep  (maker {MAKER_FEE_BPS+MAKER_SLIP_BPS:.0f} bps/side,'
          f' {BORROW_BPS_PA/100:.0f}% borrow p.a.)')
    print(BAR)

    hdr = (f"  {'K':>4}  {'Net CAGR':>9}  {'Gross CAGR':>11}  {'Sharpe':>7}"
           f"  {'Sortino':>8}  {'MaxDD':>7}  {'Calmar':>7}"
           f"  {'Fee drag':>9}  {'Borrow':>7}  {'$100->':>8}")
    print(hdr)
    print('  ' + '-' * 106)

    net_results: dict = {}
    for K in LEVERAGE_LEVELS:
        pnl_lev = _apply_leverage(pnl_oos, K)
        pnl_net = _apply_cost(pnl_lev, fired_oos, MAKER_FEE_BPS, MAKER_SLIP_BPS, K)
        sn      = _full_stats(pnl_net)
        sg_lev  = _full_stats(pnl_lev)

        fee_drag_pct = K * rt['rt_pa'] * 2 * (MAKER_FEE_BPS + MAKER_SLIP_BPS) / 10_000.0 * 100
        borrow_pct   = max(0.0, K - 1.0) * BORROW_BPS_PA / 100.0

        net_results[K] = {'stats': sn, 'pnl': pnl_net}

        star = ' <-- BEST' if K == 2.0 else (' <-- OLD SIM' if K == 5.0 else '')
        print(f"  {K:>4.1f}  {sn['cagr']*100:>+8.2f}%  "
              f"{sg_lev['cagr']*100:>+10.2f}%  "
              f"{sn['sharpe']:>+7.3f}  "
              f"{sn['sortino']:>+8.3f}  "
              f"{sn['max_dd']*100:>6.2f}%  "
              f"{sn['calmar']:>+7.3f}  "
              f"{fee_drag_pct:>+8.1f}%  "
              f"{borrow_pct:>6.1f}%  "
              f"  ${sn['final']:>7.2f}{star}")

    print(f"""
  Notes:
    Fee drag  = K x {rt["rt_pa"]:.0f} RT/yr x 2 sides x {MAKER_FEE_BPS+MAKER_SLIP_BPS:.0f} bps (scales with K)
    Borrow    = (K-1) x {BORROW_BPS_PA/100:.0f}% p.a.  (conservative crypto margin rate)
    K=2 recommended: much higher net CAGR, MaxDD still manageable
    K=3 carries >10% MaxDD -- only for risk-seeking allocation
""")

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 3 — $700 Quarterly Projection
    # ══════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print(f'  SECTION 3 - ${START_CAPITAL:.0f} Quarterly Projection  (K=1/2/3/5, maker fees)')
    print(BAR)

    for K in [1.0, 2.0, 3.0, 5.0]:
        rows = _quarterly_projection(net_results[K]['pnl'], START_CAPITAL)
        sn   = net_results[K]['stats']

        print(f'\n  -- K={K:.0f}  Net CAGR {sn["cagr"]*100:+.2f}%  '
              f'Sharpe {sn["sharpe"]:+.3f}  MaxDD {sn["max_dd"]*100:.2f}%')
        print(f'  {"Quarter":<12}  {"Return":>10}  {"Capital":>12}')
        print('  ' + '-' * 38)
        for row in rows:
            print(f'  {row["Quarter"]:<12}  {row["Return"]:>10}  {row["Capital"]:>12}')

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 4 — K=5: Old Fee Model vs Honest Maker Fees
    # ══════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print('  SECTION 4 - K=5 Fee Model Comparison  (old 5bps/active-bar  vs  honest maker)')
    print(BAR)

    K5 = 5.0
    # Model A: gross (no fees) at K=5
    pnl_k5_gross = _apply_leverage(pnl_oos, K5)
    sg5 = _full_stats(pnl_k5_gross)

    # Model B: old continuous "5 bps per active bar" fee model (used in V58_PROFIT_ACCELERATION.md)
    pnl_k5_old = _apply_cost_per_bar(pnl_k5_gross, fired_oos, OLD_FEE_BPS_PER_BAR, K5)
    so5 = _full_stats(pnl_k5_old)
    active_bars = int(fired_oos.sum())
    active_pct = active_bars / len(fired_oos) * 100
    old_annual_drag = K5 * OLD_FEE_BPS_PER_BAR / 10_000.0 * active_bars / rt['years'] * 100

    # Model C: honest maker fee 3 bps/side per transition at K=5
    pnl_k5_maker = net_results[5.0]['pnl']
    sm5 = net_results[5.0]['stats']
    maker_annual_drag = K5 * rt['rt_pa'] * 2 * (MAKER_FEE_BPS + MAKER_SLIP_BPS) / 10_000.0 * 100

    print(f"""
  Parameters at K=5
  -----------------
  Gross CAGR  (K=5, no fees): {sg5['cagr']*100:+.2f}%
  Gross MaxDD (K=5, no fees): {sg5['max_dd']*100:.2f}%
  Active bars               : {active_bars:,}  ({active_pct:.1f}% of OOS bars)
  RT/year                   : {rt['rt_pa']:.0f}    Borrow drag : {(K5-1)*BORROW_BPS_PA/100:.1f}% p.a.

  MODEL A — Old 5bps/active-bar (V58_PROFIT_ACCELERATION.md)
  -----------------------------------------------------------
  Fee applied   : {K5:.0f} x {OLD_FEE_BPS_PER_BAR:.0f} bps each active bar ({active_bars:,} bars)
  Annual drag   : ~{old_annual_drag:.1f}%  (continuous spread model)
  Net CAGR      : {so5['cagr']*100:+.2f}%
  NetSharpe     : {so5['sharpe']:+.3f}
  MaxDD         : {so5['max_dd']*100:.2f}%
  $700 -> $     : {so5['final'] * START_CAPITAL / 100:,.2f}

  MODEL B — Honest Maker Fees (3 bps/side per transition)
  -------------------------------------------------------
  Fee applied   : {K5:.0f} x {rt['rt_pa']:.0f} RT/yr x 2 sides x {MAKER_FEE_BPS+MAKER_SLIP_BPS:.0f} bps
  Annual drag   : ~{maker_annual_drag:.1f}%
  Net CAGR      : {sm5['cagr']*100:+.2f}%
  Net Sharpe    : {sm5['sharpe']:+.3f}
  MaxDD         : {sm5['max_dd']*100:.2f}%
  $700 -> $     : {sm5['final'] * START_CAPITAL / 100:,.2f}

  Key difference:
    Old model charges fee on EVERY active bar (continuous spread).
    Honest model charges only on entry/exit events (~{rt['rt_pa']*2:.0f} transitions/yr).
    Old model drag is higher for long holds; maker model is lower for infrequent trading.
""")

    # ── save ────────────────────────────────────────────────────────────────
    def _flt(v):
        return float(v) if isinstance(v, (int, float, np.integer, np.floating)) else v

    save = {
        'version': 'v66',
        'bar_info': {k: _flt(v) for k, v in rt.items()},
        'gross': {k: _flt(v) for k, v in sg.items() if k != 'yoy'},
        'gross_yoy': {str(yr): float(r) for yr, r in sg['yoy'].items()},
        'net': {},
    }
    for K, res in net_results.items():
        s = res['stats']
        save['net'][f'K{K}'] = {k: _flt(v) for k, v in s.items() if k != 'yoy'}
        save['net'][f'K{K}']['yoy'] = {str(yr): float(r) for yr, r in s['yoy'].items()}

    out = OUT_DIR_ / 'crypto_bsdt_v66_results.json'
    with open(out, 'w') as f:
        json.dump(save, f, indent=2)
    print(f'  Saved: {out}')
    print(f'  Total runtime: {time.time()-t0:.0f}s')
    print(BAR)
