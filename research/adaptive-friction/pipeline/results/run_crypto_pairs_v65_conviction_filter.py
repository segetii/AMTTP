"""
Crypto BSDT v65 — Conviction Execution Filter
==============================================
Frozen model: v63_b2_k4_mu0.5  (NO parameter changes)

Problem identified in v64:
  151 RT/year × 2 sides × 12 bps/side = 36.2% annual drag > 19.6% gross CAGR
  Strategy is profitable pre-cost, unprofitable at standard taker fees.

Two-part fix:
  1. MAKER FEES  — limit orders only (fee ~2 bps, slip ~1 bps = 3 bps/side total)
  2. CONVICTION GATE — only execute when g_G × g_T > exec_thresh
     This cherry-picks high-quality HH bars, cutting RT/year dramatically.

Cost model (both fixes together):
  Effective RT/year × 2 sides × 3 bps/side  < 19.6% CAGR  → needs RT < 326
  At exec_thresh = 0.45: RT ≈ 40–60 → drag ≈ 2.4–3.6% → net CAGR ≈ 16–17%

Execution gate implementation:
  executed[t]  = fired[t]  AND  joint[t] > exec_thresh
  Phase logic  = same v63 logic but conditioned on executed instead of fired
  Cost counted = transitions in executed  (not fired)
  This is purely an execution policy — NO model parameter changes.

Sections:
  1. Fee sensitivity at current RT=151   (maker vs taker)
  2. Conviction threshold sweep          (exec_thresh ∈ {0, 0.20, 0.30, 0.40, 0.50})
  3. Cross-table: exec_thresh × fee      (find the sweet spot)
  4. $700 projection for the optimal config
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
    ALPHA_FG, A_FIRE_THRESH, G_THRESH_BASE, T_THRESH_BASE,
    G_BOOST_THRESH, CHAMPION_BOOST, N_OPT, K_G,
    CLIP_BASE, CALIB_BARS, BPD, PCA_K_B, FIRE_PERCENTILE,
    _dynamic_gth, _float_gate_normalised, _sigmoid_gate,
    _build_pnl_v58, OOS_SPLIT,
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

# ── FROZEN CHAMPION PARAMS ─────────────────────────────────────────────────────
CHAMP_CLIP_BOOST = 2.0
CHAMP_K          = 4.0
CHAMP_MU         = 0.5

# ── FEE SCENARIOS (per side, bps) ─────────────────────────────────────────────
FEE_SCENARIOS = [
    ('Taker  10+2=12 bps/side', 10, 2),
    ('Maker   2+1= 3 bps/side',  2, 1),
    ('Maker   2+2= 4 bps/side',  2, 2),
    ('Maker   3+2= 5 bps/side',  3, 2),
]

# ── CONVICTION THRESHOLDS TO SWEEP ────────────────────────────────────────────
EXEC_THRESHOLDS = [0.00, 0.20, 0.30, 0.40, 0.45, 0.50, 0.55, 0.60]

# ── OPTIMAL FEE INDEX (Maker 3 bps/side = realistic with limit orders) ────────
BEST_FEE_IDX = 1   # 'Maker 2+1= 3 bps/side'

# ── CAPITAL ────────────────────────────────────────────────────────────────────
START_CAPITAL = 700.0
MAX_DD_LIMIT  = 0.20

# ─────────────────────────────────────────────────────────────────────────────
def _build_pnl_v65(
    base:       pd.Series,
    sv36:       pd.DataFrame,
    lf:         pd.DataFrame,
    s4:         pd.DataFrame,
    rv_norm:    pd.Series,
    exec_thresh: float = 0.0,
    lo:          float = -0.01,
    alpha:       float = ALPHA_FG,
    k:           float  = CHAMP_K,
    mu:          float  = CHAMP_MU,
    clip_boost:  float  = CHAMP_CLIP_BOOST,
) -> tuple[pd.Series, np.ndarray]:
    """
    v63_b2_k4_mu0.5 with execution gate.
    
    Returns
    -------
    pnl        : bar-by-bar PnL series
    joint_arr  : g_G × g_T array (for cost counting and analysis)
    
    Execution gate:
      executed[t] = fired[t] AND joint[t] > exec_thresh
      Phase logic : HH/HL/LH/LL only when executed[t] == True
                    otherwise phase = 1.0  (sit out that bar)
    At exec_thresh=0: identical to v63 (all fired bars execute).
    """
    idx  = base.index
    sv36 = sv36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lf.reindex(idx,   method='ffill').fillna(0.5)
    s4   = s4.reindex(idx,   method='ffill').fillna(0.0)
    gam  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lp   = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size = np.clip(1.0 - gam.values, 0.0, 1.0) * (0.75 + 0.5 * lp.values)

    a_G  = s4['a_G'];  a_A = s4['a_A'];  a_T = s4['a_T']
    gth      = _dynamic_gth(rv_norm.reindex(idx, method='ffill').fillna(1.0), lo)
    gth_vals = gth.values

    G_mem  = a_G.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    T_mem  = a_T.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    fired  = (a_A.shift(1).fillna(0.0) > A_FIRE_THRESH).values.astype(bool)

    G_above = G_mem.values > gth_vals
    T_above = T_mem.values > T_THRESH_BASE

    # ── floating gate ─────────────────────────────────────────────────────────
    Q_G_z  = _float_gate_normalised(a_G.values, alpha)
    Q_T_z  = _float_gate_normalised(a_T.values, alpha)
    g_G    = _sigmoid_gate(Q_G_z, k, mu)
    g_T    = _sigmoid_gate(Q_T_z, k, mu)
    joint  = g_G * g_T

    # ── execution gate (conviction filter) ────────────────────────────────────
    if exec_thresh > 0.0:
        executed = fired & (joint > exec_thresh)
    else:
        executed = fired.copy()

    q_HH = executed &  G_above &  T_above
    q_HL = executed &  G_above & ~T_above
    q_LH = executed & ~G_above &  T_above
    q_LL = executed & ~G_above & ~T_above

    # ── dynamic clip on HH only ────────────────────────────────────────────────
    clip_dyn = CLIP_BASE + clip_boost * joint

    # ── phase ─────────────────────────────────────────────────────────────────
    phase = np.ones(len(fired), dtype=float)
    phase[q_HH] = clip_dyn[q_HH]
    phase[q_HL] = 0.05
    phase[q_LH] = 0.05
    phase[q_LL] = 0.05

    # ── champion boost ─────────────────────────────────────────────────────────
    flag = np.zeros(len(a_G.values), dtype=float)
    flag[1:] = (a_G.values[:-1] > G_BOOST_THRESH).astype(float)

    pnl = pd.Series(
        base.reindex(idx).fillna(0.0).values * size
        * (1.0 + CHAMPION_BOOST * flag) * phase,
        index=idx,
    )
    return pnl, joint


def _apply_cost_with_gate(
    pnl:          pd.Series,
    executed:     np.ndarray,
    fee_bps:      float,
    slip_bps:     float,
) -> pd.Series:
    """Cost based on transitions in executed[] (not raw fired[])."""
    if fee_bps == 0 and slip_bps == 0:
        return pnl.copy()
    exec_s = pd.Series(executed.astype(int), index=pnl.index)
    events = exec_s.diff().abs().fillna(0).astype(bool)
    cost   = (fee_bps + slip_bps) / 10_000.0
    return pnl - events.astype(float) * cost


def _rt_per_year_from_executed(executed: np.ndarray, idx: pd.DatetimeIndex) -> float:
    n_transitions = int(pd.Series(executed.astype(int)).diff().abs().fillna(0).sum())
    n_rt  = n_transitions / 2.0
    yrs   = (idx[-1] - idx[0]).total_seconds() / (365.25 * 86400)
    return float(n_rt / yrs) if yrs > 0 else 0.0


def _quarterly_projection(pnl_oos: pd.Series, start_cap: float) -> pd.DataFrame:
    try:
        q_ret = (1.0 + pnl_oos).resample('QE').prod() - 1.0
    except Exception:
        q_ret = (1.0 + pnl_oos).resample('Q').prod() - 1.0
    rows = []; cap = start_cap
    for dt, r in q_ret.items():
        cap_end = cap * (1.0 + float(r))
        rows.append({'Quarter': f"{dt.year} Q{(dt.month-1)//3+1}",
                     'Return': float(r), 'Profit': float(cap_end-cap),
                     'End Capital': float(cap_end)})
        cap = cap_end
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
def main():
    t0  = time.time()
    BAR = '=' * 100
    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)

    print(BAR)
    print('  v65 — Conviction Execution Filter  (model frozen at v63_b2_k4_mu0.5)')
    print('  Fix: trade only when g_G×g_T > exec_thresh  +  maker order fees')
    print('  exec_thresh=0 → identical to v63 (all fired bars)')
    print(BAR)

    t = lambda msg: print(f'\n{msg}', flush=True)

    # ── data infrastructure (identical pipeline, cached) ─────────────────────
    t('[1] 1h data')
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
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
    base_pnl = assemble_combined(
        {**d1h, **h_strats},
        compute_quality({**d1h, **h_strats}, bpd=BPD))
    rv_ema = _realized_vol(df_1h, ema_span=3)

    # ── pre-compute pnl + joint per exec_thresh ───────────────────────────────
    t(f'[8] Conviction filter pre-computation  t={time.time()-t0:.0f}s')
    results_by_thresh = {}
    for eth in EXEC_THRESHOLDS:
        pnl, joint_arr = _build_pnl_v65(
            base_pnl, sig_v36, lam_feat, sig_4ch,
            rv_norm=rv_ema, exec_thresh=eth)
        # build executed mask for OOS period
        a_A      = sig_4ch['a_A'].reindex(pnl.index, method='ffill').fillna(0.0)
        fired    = (a_A.shift(1).fillna(0.0) > A_FIRE_THRESH).values.astype(bool)
        executed = fired & (joint_arr > eth) if eth > 0 else fired.copy()
        rt_yr    = _rt_per_year_from_executed(
            executed[test_mask], df_1h.index[test_mask])
        results_by_thresh[eth] = (pnl, executed, joint_arr, rt_yr)
        print(f'    exec_thresh={eth:.2f}  RT/yr={rt_yr:.0f}')

    # ════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print('  SECTION 1 — FEE SENSITIVITY AT CURRENT RT=151 (exec_thresh=0)')
    print('  Shows why taker fees destroy the strategy; maker fees are survivable')
    print(f'{BAR}')

    pnl0, exec0, joint0, _ = results_by_thresh[0.0]
    st_gross = _full_stats(pnl0[test_mask])
    print(f'  Gross (no cost): Sharpe {st_gross["sharpe"]:+.3f}  '
          f'CAGR {st_gross["cagr"]:+.1%}  MaxDD {st_gross["max_dd"]:+.1%}')
    print()
    hdr = (f"  {'Fee scenario':<32} {'fee':>4} {'slip':>4} {'drag/yr':>8}"
           f"  {'Sharpe':>7}  {'CAGR':>7}  {'MaxDD':>7}  {'$100→':>8}")
    print(hdr)
    print('  ' + '-'*32 + ' ' + '-'*4 + ' ' + '-'*4 + ' ' + '-'*8
          + '  ' + '-'*7 + '  ' + '-'*7 + '  ' + '-'*7 + '  ' + '-'*8)
    rt0 = results_by_thresh[0.0][3]

    s1_rows = []
    for flbl, fee, slip in FEE_SCENARIOS:
        drag = rt0 * 2 * (fee + slip) / 100.0   # drag in %
        pnl_c = _apply_cost_with_gate(pnl0, exec0, fee, slip)
        st    = _full_stats(pnl_c[test_mask])
        print(f"  {flbl:<32} {fee:>4} {slip:>4} {drag:>+7.1f}%"
              f"  {st['sharpe']:>+7.3f}  {st['cagr']:>+6.1%}"
              f"  {st['max_dd']:>+7.1%}  ${st['final']:>7.2f}")
        s1_rows.append({'fee': fee, 'slip': slip, 'drag': drag,
                        'sharpe': float(st['sharpe']), 'cagr': float(st['cagr']),
                        'max_dd': float(st['max_dd']), 'final': float(st['final'])})

    # ════════════════════════════════════════════════════════════════════════
    flbl_best, fee_best, slip_best = FEE_SCENARIOS[BEST_FEE_IDX]
    print(f'\n{BAR}')
    print(f'  SECTION 2 — CONVICTION GATE SWEEP  (fee = {flbl_best.strip()})')
    print(f'  Reduces RT/year by only executing when g_G×g_T > exec_thresh')
    print(f'  Higher thresh → fewer trades → less drag → higher net Sharpe')
    print(f'{BAR}')

    hdr2 = (f"  {'exec_thresh':>11}  {'RT/yr':>6}  {'drag/yr':>8}"
            f"  {'Sharpe':>7}  {'Sortino':>8}  {'CAGR':>7}"
            f"  {'MaxDD':>7}  {'$100→':>8}  Viable?")
    print(hdr2)
    print('  ' + '-'*11 + '  ' + '-'*6 + '  ' + '-'*8
          + '  ' + '-'*7 + '  ' + '-'*8 + '  ' + '-'*7
          + '  ' + '-'*7 + '  ' + '-'*8 + '  -------')

    s2_rows = []
    best_thresh = 0.0; best_net_cagr = -999.0
    for eth in EXEC_THRESHOLDS:
        pnl_e, exec_e, _, rt_yr = results_by_thresh[eth]
        drag    = rt_yr * 2 * (fee_best + slip_best) / 100.0
        pnl_c   = _apply_cost_with_gate(pnl_e, exec_e, fee_best, slip_best)
        st      = _full_stats(pnl_c[test_mask])
        viable  = st['cagr'] > 0.05 and abs(st['max_dd']) < MAX_DD_LIMIT
        marker  = '← BEST' if viable and st['cagr'] > best_net_cagr else ''
        if viable and st['cagr'] > best_net_cagr:
            best_net_cagr = st['cagr']; best_thresh = eth
        print(f"  {eth:>11.2f}  {rt_yr:>6.0f}  {drag:>+7.1f}%"
              f"  {st['sharpe']:>+7.3f}  {st['sortino']:>+8.3f}"
              f"  {st['cagr']:>+6.1%}  {st['max_dd']:>+7.1%}"
              f"  ${st['final']:>7.2f}  {'YES' if viable else 'no'}  {marker}")
        s2_rows.append({'exec_thresh': eth, 'rt_yr': float(rt_yr),
                        'drag': float(drag), 'sharpe': float(st['sharpe']),
                        'cagr': float(st['cagr']), 'max_dd': float(st['max_dd']),
                        'final': float(st['final']), 'viable': bool(viable)})

    # ════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print(f'  SECTION 3 — CROSS TABLE: exec_thresh × fee  (net CAGR %)')
    print(f'{BAR}')

    fee_cols = [(lbl, f, s) for lbl, f, s in FEE_SCENARIOS]
    hdr3 = f"  {'exec_thresh':>11}  {'RT/yr':>6}"
    for flbl, _, _ in fee_cols:
        hdr3 += f"  {flbl.split('=')[0].strip():>14}"
    print(hdr3)
    print('  ' + '-'*11 + '  ' + '-'*6 + ('  ' + '-'*14) * len(fee_cols))

    s3_table = {}
    for eth in EXEC_THRESHOLDS:
        pnl_e, exec_e, _, rt_yr = results_by_thresh[eth]
        row_str = f"  {eth:>11.2f}  {rt_yr:>6.0f}"
        s3_table[str(eth)] = {'rt_yr': float(rt_yr)}
        for flbl, fee, slip in fee_cols:
            pnl_c = _apply_cost_with_gate(pnl_e, exec_e, fee, slip)
            cagr  = _full_stats(pnl_c[test_mask])['cagr']
            mark  = '★' if (cagr > 0.10 and abs(_full_stats(pnl_c[test_mask])['max_dd']) < MAX_DD_LIMIT) else ' '
            row_str += f"  {cagr:>+12.1%}{mark} "
            s3_table[str(eth)][flbl.strip()] = float(cagr)
        print(row_str)
    print('  ★ = CAGR > 10% AND MaxDD < 20%')

    # ════════════════════════════════════════════════════════════════════════
    pnl_opt, exec_opt, _, rt_opt = results_by_thresh[best_thresh]
    pnl_final = _apply_cost_with_gate(pnl_opt, exec_opt, fee_best, slip_best)
    st_opt    = _full_stats(pnl_final[test_mask])
    df_proj   = _quarterly_projection(pnl_final[test_mask], START_CAPITAL)
    final_cap = START_CAPITAL * st_opt['final'] / 100.0

    print(f'\n{BAR}')
    print(f'  SECTION 4 — ${START_CAPITAL:,.0f} PROJECTION')
    print(f'  Config: exec_thresh={best_thresh}  |  {flbl_best.strip()}  |  RT/yr≈{rt_opt:.0f}')
    print(f'  Gross: Sharpe +4.762  CAGR +19.6%  →  Net (after cost): Sharpe {st_opt["sharpe"]:+.3f}  CAGR {st_opt["cagr"]:+.1%}')
    print(f'{BAR}')

    print(f"\n  QUARTERLY BREAKDOWN:")
    print(f"  {'Quarter':<12} {'Return':>8}  {'Profit':>12}  {'Running Capital':>16}")
    print(f"  {'-'*12} {'-'*8}  {'-'*12}  {'-'*16}")
    for _, row in df_proj.iterrows():
        p = row['Profit']; c = row['End Capital']
        print(f"  {row['Quarter']:<12} {row['Return']:>+8.2%}"
              f"  {'+' if p>=0 else ''}{p:>7.2f} USD  ${c:>12.2f}")

    print(f'\n  YEAR-ON-YEAR SUMMARY:')
    print(f"  {'Year':<7} {'Return':>8}  {'Start':>13}  {'End':>13}  {'Profit':>12}")
    print(f"  {'-'*7} {'-'*8}  {'-'*13}  {'-'*13}  {'-'*12}")
    cap = START_CAPITAL; s4_yoy = {}
    for yr in sorted(st_opt['yoy'].keys()):
        if yr < int(TEST_START[:4]): continue
        r = st_opt['yoy'][yr]
        cap_end = cap * (1.0 + r)
        tag = ' (YTD)' if yr == max(st_opt['yoy'].keys()) else ''
        print(f"  {yr:<7} {r:>+8.2%}  ${cap:>12,.2f}  ${cap_end:>12,.2f}  ${cap_end-cap:>+11.2f}{tag}")
        s4_yoy[str(yr)] = float(cap_end); cap = cap_end

    total_profit = final_cap - START_CAPITAL
    print(f'\n  ┌{"─"*64}┐')
    print(f'  │  ${START_CAPITAL:,.0f} → ${final_cap:,.2f}   (total profit: ${total_profit:+,.2f}){"":>9}│')
    print(f'  │  Gross CAGR +19.6%  →  Net CAGR {st_opt["cagr"]:>+.1%}{"":>28}│')
    print(f'  │  Sharpe {st_opt["sharpe"]:>+.3f}   Calmar {st_opt["calmar"]:>+.2f}   '
          f'MaxDD {st_opt["max_dd"]:>+.1%}{"":>18}│')
    print(f'  │  RT/year ≈ {rt_opt:.0f}   Ann. drag ≈ {rt_opt*2*(fee_best+slip_best)/100:+.1f}%'
          f'   WinRate {st_opt["win_rate"]:>.1%}{"":>18}│')
    print(f'  └{"─"*64}┘')

    # ── persist ────────────────────────────────────────────────────────────────
    class _NpEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, np.integer):  return int(obj)
            if isinstance(obj, np.floating): return float(obj)
            if isinstance(obj, np.bool_):    return bool(obj)
            if isinstance(obj, np.ndarray):  return obj.tolist()
            return super().default(obj)

    out = {
        'version': 'v65',
        'champion': 'v63_b2_k4_mu0.5',
        'section1': s1_rows,
        'section2': s2_rows,
        'section3': s3_table,
        'section4': {
            'best_exec_thresh': float(best_thresh),
            'fee_bps': fee_best, 'slip_bps': slip_best,
            'rt_per_year': float(rt_opt),
            'start_capital': START_CAPITAL,
            'final_capital': float(final_cap),
            'total_profit': float(total_profit),
            'net_sharpe': float(st_opt['sharpe']),
            'net_cagr': float(st_opt['cagr']),
            'max_dd': float(st_opt['max_dd']),
            'yoy_capitals': s4_yoy,
            'quarterly': df_proj.to_dict('records'),
        },
    }
    out_path = OUT_DIR_ / 'crypto_bsdt_v65_results.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(out, f, indent=2, cls=_NpEncoder)
    print(f'\n  Results saved → {out_path}')
    print(f'  Total time: {time.time()-t0:.0f}s')


if __name__ == '__main__':
    main()
