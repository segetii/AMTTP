"""
Crypto BSDT v64 — Execution Cost & Leverage Analysis
=====================================================
Frozen champion: v63_b2_k4_mu0.5  (CLIP_BOOST=2, k=4, μ=0.5, α=0.85)
NO parameter changes.  Analysis only.

SECTION 1 — Execution cost impact  (4 cost scenarios, K=1)
SECTION 2 — Leverage sweep          K ∈ {1, 2, 3, 5, 7, 10}
SECTION 3 — $700 projection         quarterly + YoY for optimal K

Cost model
----------
Each fired→not-fired or not-fired→fired transition = one side of a round trip.
  Entry costs:  fee_bps + slip_bps  (one-way)
  Exit  costs:  fee_bps + slip_bps  (one-way)
  Full RT cost: 2 × (fee_bps + slip_bps)

Leverage model
--------------
  Levered bar return  = K × raw_return  −  (K−1) × borrow_rate_daily / 24
  Borrow rate default : 0.01 % / day  ≈ 3.65 % / year  (CEX margin, conservative)
  Selection criterion : max Sharpe  where  OOS MaxDD ≤ 20 %
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

# ── import all infrastructure from v63 ────────────────────────────────────────
from run_crypto_pairs_v63_clip_boost import (
    _build_pnl_v63, _realized_vol, _full_stats, ANN_1H,
    ALPHA_FG, A_FIRE_THRESH, OOS_SPLIT,
    _make_cached_fetch, _cached_fetch_and_prepare,
    _cached_add_cross_market, _cached_fetch_binance_funding,
)
import run_crypto_pairs_v63_clip_boost as _v63mod
import run_crypto_pairs_v34_full_combined as _v34mod

OUT_DIR    = _v34mod.OUT_DIR
TEST_START = _v34mod.TEST_START
TRAIN_START = _v34mod.TRAIN_START
TRAIN_END   = _v34mod.TRAIN_END
CALIB_BARS  = _v63mod.CALIB_BARS
BPD         = _v63mod.BPD
PCA_K_B     = _v63mod.PCA_K_B
FIRE_PERCENTILE = _v63mod.FIRE_PERCENTILE
OUT_DIR_    = Path(OUT_DIR)

# ── FROZEN CHAMPION ────────────────────────────────────────────────────────────
CHAMP_CLIP_BOOST = 2.0
CHAMP_K          = 4.0
CHAMP_MU         = 0.5

# ── COST SCENARIOS  (fee_bps/side, slip_bps/side) ─────────────────────────────
COST_SCENARIOS = [
    ('No cost  (backtest baseline)  ',   0,   0),
    ('Low    6 + 1 =  7 bps / side  ',   6,   1),
    ('Mid   10 + 2 = 12 bps / side  ',  10,   2),
    ('High  10 + 5 = 15 bps / side  ',  10,   5),
]
REALISTIC_COST_IDX = 2          # "Mid" used for leverage sweep and $700 projection

# ── LEVERAGE GRID ──────────────────────────────────────────────────────────────
LEVERAGE_GRID     = [1, 2, 3, 5, 7, 10]
BORROW_RATE_DAILY = 0.0001      # 0.01 % / day ≈ 3.65 % / year
MAX_DD_LIMIT      = 0.20        # hard cap for K selection

# ── STARTING CAPITAL ──────────────────────────────────────────────────────────
START_CAPITAL = 700.0


# ─────────────────────────────────────────────────────────────────────────────
def _apply_cost(
    pnl:     pd.Series,
    sig_4ch: pd.DataFrame,
    fee_bps: float,
    slip_bps: float,
) -> pd.Series:
    """Subtract (fee + slip) on every fired-state transition (one side per event)."""
    if fee_bps == 0 and slip_bps == 0:
        return pnl.copy()
    a_A   = sig_4ch['a_A'].reindex(pnl.index, method='ffill').fillna(0.0)
    fired = (a_A.shift(1).fillna(0.0) > A_FIRE_THRESH)
    events = fired.astype(int).diff().abs().fillna(0).astype(bool)
    cost   = (fee_bps + slip_bps) / 10_000.0
    return pnl - events.astype(float) * cost


def _apply_leverage(pnl: pd.Series, K: float) -> pd.Series:
    """K× the returns, subtract borrow cost on (K−1) borrowed fraction every bar."""
    if K == 1.0:
        return pnl.copy()
    borrow = (K - 1.0) * BORROW_RATE_DAILY / 24.0
    return pd.Series(pnl.values * K - borrow, index=pnl.index)


def _count_rt_per_year(pnl_oos: pd.Series, sig_4ch: pd.DataFrame) -> float:
    """Empirical round-trips per year over the OOS window."""
    a_A   = sig_4ch['a_A'].reindex(pnl_oos.index, method='ffill').fillna(0.0)
    fired = (a_A.shift(1).fillna(0.0) > A_FIRE_THRESH)
    n_transitions = int(fired.astype(int).diff().abs().fillna(0).sum())
    n_rt  = n_transitions / 2.0
    yrs   = (pnl_oos.index[-1] - pnl_oos.index[0]).total_seconds() / (365.25 * 86400)
    return float(n_rt / yrs) if yrs > 0 else 0.0


def _quarterly_projection(pnl_oos: pd.Series, start_cap: float) -> pd.DataFrame:
    """Quarter-by-quarter capital table starting from start_cap."""
    try:
        q_ret = (1.0 + pnl_oos).resample('QE').prod() - 1.0
    except Exception:
        q_ret = (1.0 + pnl_oos).resample('Q').prod() - 1.0
    rows = []
    cap  = start_cap
    for dt, r in q_ret.items():
        cap_end = cap * (1.0 + float(r))
        rows.append({
            'Quarter':     f"{dt.year} Q{(dt.month - 1) // 3 + 1}",
            'Return':      float(r),
            'Profit':      float(cap_end - cap),
            'End Capital': float(cap_end),
        })
        cap = cap_end
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
def main():
    t0  = time.time()
    BAR = '=' * 100
    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)

    print(BAR)
    print('  v64 — Execution Cost & Leverage Analysis')
    print('  Frozen champion: v63_b2_k4_mu0.5  (CLIP_BOOST=2, k=4, μ=0.5, α=0.85)')
    print('  Cost: per-side bps  |  Leverage: multiplied returns minus borrow drag')
    print(BAR)

    t = lambda msg: print(f'\n{msg}', flush=True)

    # ── data (identical to v63 boilerplate) ─────────────────────────────────
    t('[1] 1h data')
    df_1h, has_sol = _v63mod.build_1h_df(start='2021-01-01', end='2026-05-01')
    test_mask   = df_1h.index >= TEST_START
    train_1h    = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    second_half = df_1h.index >= OOS_SPLIT

    t(f'[2] Funding  t={time.time()-t0:.0f}s')
    try:
        fund     = _cached_fetch_binance_funding()
        fund_eth = fund.get('ETHUSDT'); fund_btc = fund.get('BTCUSDT')
    except Exception as e:
        print(f'    Warning: {e}'); fund_eth = fund_btc = None

    t(f'[3] State panel  t={time.time()-t0:.0f}s')
    X = _v63mod.build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X = np.nan_to_num(X)
    train_idx  = np.where(train_1h)[0]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[train_idx[-CALIB_BARS:]] = True

    t(f'[4] Engine  t={time.time()-t0:.0f}s')
    M, net, geom, lyap, ews, stoch, e_star, theta = _v63mod.calibrate_intraday_engine(X, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)
    M_k1    = _v63mod.MasterOperator.calibrate(X[calib_mask], k=PCA_K_B)

    t(f'[5] Signals  t={time.time()-t0:.0f}s')
    sig_v36       = _v63mod.compute_intraday_signals(X, df_1h, M, net, ews, stoch, e_star, theta)
    sig_v37, _, _ = _v63mod.compute_price_prediction_signals(X, df_1h, M, sig_v36, e_star, sigma_n)
    lam_feat      = _v63mod.compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))

    t(f'[6] 4-channel  t={time.time()-t0:.0f}s')
    mu_norm  = _v63mod.calibrate_channel_means(X, calib_mask, M_k1)
    fire_thr = _v63mod.calibrate_firing_thresholds(X, calib_mask, M_k1, pct=FIRE_PERCENTILE)
    sig_4ch  = _v63mod.compute_four_channel_signals_v39b(X, df_1h, M_k1, sig_v36, fire_thr, mu_norm)

    t(f'[7] Base portfolio  t={time.time()-t0:.0f}s')
    h_strats = _v63mod.compute_1h_strategies(df_1h, has_sol)
    df_d     = _cached_fetch_and_prepare()
    df_d     = _cached_add_cross_market(df_d)
    fund_d   = _cached_fetch_binance_funding()
    df_d     = _v63mod.add_leverage_features(df_d, fund_d)
    tmask_d  = (df_d.index >= TRAIN_START) & (df_d.index <= TRAIN_END)
    pos_dict, _, F_daily, gate_daily = _v63mod.build_daily_positions(
        df_d, tmask_d, np.asarray(tmask_d, dtype=bool))
    instr_map = {
        'D1_trend_eth': df_1h['ret_eth'],
        'D2_pairs_eb':  df_1h['spread_ret_eb'],
        'D3_pairs_es':  df_1h['ret_eth'] - df_1h.get('ret_sol', df_1h['ret_eth']),
        'D4_macro_btc': df_1h['ret_btc'],
        'D5_macro_btc': df_1h['ret_btc'],
        'D5_macro_alt': df_1h['ret_eth'],
    }
    d1h = {n: _v63mod.upsample_daily_to_1h_pnl(p, instr_map.get(n, df_1h['ret_eth']), gate_daily)
           for n, p in pos_dict.items()}
    base_pnl = _v63mod.assemble_combined(
        {**d1h, **h_strats},
        _v63mod.compute_quality({**d1h, **h_strats}, bpd=BPD))
    rv_ema = _realized_vol(df_1h, ema_span=3)

    # ── frozen champion PnL ──────────────────────────────────────────────────
    t(f'[8] Frozen champion PnL  t={time.time()-t0:.0f}s')
    pnl_raw = _build_pnl_v63(
        base_pnl, sig_v36, lam_feat, sig_4ch,
        rv_norm=rv_ema, lo=-0.01,
        clip_boost=CHAMP_CLIP_BOOST, k=CHAMP_K, mu=CHAMP_MU, alpha=ALPHA_FG,
    )
    pnl_oos_raw = pnl_raw[test_mask]
    rt_yr = _count_rt_per_year(pnl_oos_raw, sig_4ch)
    st0   = _full_stats(pnl_oos_raw)

    print(f'    Sharpe (no cost, K=1) : {st0["sharpe"]:+.3f}')
    print(f'    CAGR                  : {st0["cagr"]:>+.1%}')
    print(f'    MaxDD                 : {st0["max_dd"]:>+.1%}')
    print(f'    Round-trips / year    : {rt_yr:.1f}')
    print(f'    RT cost at 12bps/side : ~{rt_yr * 2 * 12 / 100:.1f} bps/yr drag')

    # ═════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print(f'  SECTION 1 — EXECUTION COST IMPACT  (K=1)')
    print(f'  Champion: v63_b2_k4_mu0.5  |  RT/year ≈ {rt_yr:.0f}  |  RT cost = 2×(fee+slip)')
    print(f'{BAR}')

    hdr1 = (f"  {'Scenario':<38} {'Sharpe':>7} {'Sortino':>8} {'CAGR':>7}"
            f" {'MaxDD':>7} {'PF':>6} {'$100→':>8}  {'Ann.drag':>8}")
    print(hdr1)
    print('  ' + '-'*38 + ' ' + '-'*7 + ' ' + '-'*8 + ' ' + '-'*7
          + ' ' + '-'*7 + ' ' + '-'*6 + ' ' + '-'*8 + '  ' + '-'*8)

    s1 = {}
    for label, fee, slip in COST_SCENARIOS:
        pnl_c = _apply_cost(pnl_raw, sig_4ch, fee, slip)[test_mask]
        st    = _full_stats(pnl_c)
        drag  = st0['cagr'] - st['cagr']
        pf_s  = f"{st['profit_f']:>6.2f}" if st['profit_f'] != np.inf else "   ∞  "
        print(f"  {label:<38} {st['sharpe']:>+7.3f} {st['sortino']:>+8.3f}"
              f" {st['cagr']:>+6.1%} {st['max_dd']:>+7.1%} {pf_s} ${st['final']:>7.2f}"
              f"  {drag:>+7.1%}")
        s1[label.strip()] = dict(
            sharpe=float(st['sharpe']), sortino=float(st['sortino']),
            cagr=float(st['cagr']), max_dd=float(st['max_dd']),
            profit_f=float(st['profit_f']) if st['profit_f'] != np.inf else 99.0,
            final=float(st['final']), ann_drag=float(drag),
        )

    # choose realistic cost for subsequent sections
    r_lbl, r_fee, r_slip = COST_SCENARIOS[REALISTIC_COST_IDX]
    pnl_cost = _apply_cost(pnl_raw, sig_4ch, r_fee, r_slip)
    st_cost1 = _full_stats(pnl_cost[test_mask])
    print(f'\n  Using for Sections 2 & 3: {r_lbl.strip()}')
    print(f'  Net Sharpe after cost: {st_cost1["sharpe"]:+.3f}  '
          f'CAGR: {st_cost1["cagr"]:+.1%}  MaxDD: {st_cost1["max_dd"]:+.1%}')

    # ═════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print(f'  SECTION 2 — LEVERAGE SWEEP')
    print(f'  Costs: {r_fee}bps fee + {r_slip}bps slip per side')
    print(f'  Borrow: {BORROW_RATE_DAILY*100:.3f}%/day = {BORROW_RATE_DAILY*365*100:.2f}%/yr on (K−1) notional')
    print(f'  Criterion: max Sharpe where OOS MaxDD ≤ {MAX_DD_LIMIT:.0%}')
    print(f'{BAR}')

    hdr2 = (f"  {'K':>3}  {'Sharpe':>7}  {'Sortino':>8}  {'CAGR':>7}  {'MaxDD':>7}"
            f"  {'AvgDD':>7}  {'Calmar':>7}  {'$100→':>8}  {'Borrow/yr':>9}  Status")
    print(hdr2)
    print('  ' + '-'*3 + '  ' + '-'*7 + '  ' + '-'*8 + '  ' + '-'*7 + '  ' + '-'*7
          + '  ' + '-'*7 + '  ' + '-'*7 + '  ' + '-'*8 + '  ' + '-'*9 + '  ------')

    best_K = 1; best_K_sharpe = -999.0
    s2 = {}
    for K in LEVERAGE_GRID:
        pnl_lk = _apply_leverage(pnl_cost, float(K))[test_mask]
        st     = _full_stats(pnl_lk)
        borrow = (K - 1) * BORROW_RATE_DAILY * 365
        over   = abs(st['max_dd']) > MAX_DD_LIMIT
        if not over and st['sharpe'] > best_K_sharpe:
            best_K_sharpe = st['sharpe']; best_K = K
        pf_s = f"{st['profit_f']:>6.2f}" if st['profit_f'] != np.inf else "   ∞  "
        sel = '✗ DD>20%' if over else ('← SELECTED' if (not over and K == best_K) else '')
        print(f"  {K:>3}x {st['sharpe']:>+7.3f}  {st['sortino']:>+8.3f}"
              f"  {st['cagr']:>+6.1%}  {st['max_dd']:>+7.1%}"
              f"  {st['avg_dd']:>+7.1%}  {st['calmar']:>+7.2f}"
              f"  ${st['final']:>7.2f}  {borrow:>+8.1%}  {sel}")
        s2[f'K={K}'] = dict(
            K=int(K), sharpe=float(st['sharpe']), sortino=float(st['sortino']),
            cagr=float(st['cagr']), max_dd=float(st['max_dd']),
            calmar=float(st['calmar']), final=float(st['final']),
            borrow_ann=float(borrow), over_dd_limit=bool(over),
        )

    # Re-print selected K with marker now that we know it
    best_st = _full_stats(_apply_leverage(pnl_cost, float(best_K))[test_mask])
    print(f'\n  ✓ Selected K = {best_K}x  |  Sharpe {best_st["sharpe"]:+.3f}'
          f'  |  CAGR {best_st["cagr"]:+.1%}  |  MaxDD {best_st["max_dd"]:+.1%}')

    # ═════════════════════════════════════════════════════════════════════════
    pnl_opt     = _apply_leverage(pnl_cost, float(best_K))[test_mask]
    st_opt      = _full_stats(pnl_opt)
    df_proj     = _quarterly_projection(pnl_opt, START_CAPITAL)
    final_cap   = START_CAPITAL * st_opt['final'] / 100.0
    total_prof  = final_cap - START_CAPITAL

    print(f'\n{BAR}')
    print(f'  SECTION 3 — ${START_CAPITAL:,.0f} PROJECTION')
    print(f'  Config: v63_b2_k4_mu0.5  |  K={best_K}x  |  Costs: {r_fee}+{r_slip}bps/side')
    print(f'  Period: OOS {TEST_START} → latest data')
    print(f'{BAR}')

    # ── quarterly table ──────────────────────────────────────────────────────
    print(f'\n  QUARTERLY BREAKDOWN:')
    print(f"  {'Quarter':<12} {'Return':>8} {'Quarterly Profit':>17} {'Running Capital':>16}")
    print(f"  {'-'*12} {'-'*8} {'-'*17} {'-'*16}")
    for _, row in df_proj.iterrows():
        r = row['Return']
        p = row['Profit']
        c = row['End Capital']
        print(f"  {row['Quarter']:<12} {r:>+8.2%}  "
              f"{'+'if p>=0 else ''}{p:>7.2f} USD   "
              f"${c:>10.2f}")

    # ── year-on-year summary ─────────────────────────────────────────────────
    print(f'\n  YEAR-ON-YEAR SUMMARY:')
    print(f"  {'Year':<7} {'Return':>8}  {'Start Capital':>14}  {'End Capital':>13}  {'Profit':>12}")
    print(f"  {'-'*7} {'-'*8}  {'-'*14}  {'-'*13}  {'-'*12}")
    cap = START_CAPITAL
    s3_yoy = {}
    for yr in sorted(st_opt['yoy'].keys()):
        if yr < int(TEST_START[:4]):
            continue
        r       = st_opt['yoy'][yr]
        cap_end = cap * (1.0 + r)
        tag     = ' (YTD)' if yr == max(st_opt['yoy'].keys()) else ''
        print(f"  {yr:<7} {r:>+8.2%}  ${cap:>13,.2f}  ${cap_end:>12,.2f}  ${cap_end-cap:>+11.2f}{tag}")
        s3_yoy[str(yr)] = float(cap_end)
        cap = cap_end

    # ── summary ──────────────────────────────────────────────────────────────
    print(f'\n  ┌{"─"*60}┐')
    print(f'  │  ${START_CAPITAL:,.0f} → ${final_cap:,.2f}   (total profit: ${total_prof:+,.2f}){"":>5}│')
    print(f'  │  CAGR  {st_opt["cagr"]:>+.1%}   Sharpe {st_opt["sharpe"]:>+.3f}'
          f'   Calmar {st_opt["calmar"]:>+.2f}{"":>10}│')
    print(f'  │  MaxDD {st_opt["max_dd"]:>+.1%}   AvgDD  {st_opt["avg_dd"]:>+.1%}'
          f'   WinRate {st_opt["win_rate"]:>.1%}{"":>10}│')
    print(f'  └{"─"*60}┘')

    # ═════════════════════════════════════════════════════════════════════════
    # persist JSON
    out = {
        'version':   'v64',
        'champion':  'v63_b2_k4_mu0.5',
        'params':    {'clip_boost': CHAMP_CLIP_BOOST, 'k': CHAMP_K, 'mu': CHAMP_MU},
        'rt_per_year': float(rt_yr),
        'section1_cost_impact': s1,
        'section2_leverage_sweep': s2,
        'selected_K': int(best_K),
        'section3_projection': {
            'start_capital':  START_CAPITAL,
            'K':              int(best_K),
            'fee_bps':        r_fee,
            'slip_bps':       r_slip,
            'final_capital':  float(final_cap),
            'total_profit':   float(total_prof),
            'cagr':           float(st_opt['cagr']),
            'sharpe':         float(st_opt['sharpe']),
            'max_dd':         float(st_opt['max_dd']),
            'yoy_capitals':   s3_yoy,
            'quarterly':      df_proj.to_dict('records'),
        },
    }

    class _NpEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, np.integer):  return int(obj)
            if isinstance(obj, np.floating): return float(obj)
            if isinstance(obj, np.bool_):    return bool(obj)
            if isinstance(obj, np.ndarray):  return obj.tolist()
            return super().default(obj)

    out_path = OUT_DIR_ / 'crypto_bsdt_v64_results.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(out, f, indent=2, cls=_NpEncoder)
    print(f'\n  Results saved → {out_path}')
    print(f'  Total time: {time.time()-t0:.0f}s')


if __name__ == '__main__':
    main()
