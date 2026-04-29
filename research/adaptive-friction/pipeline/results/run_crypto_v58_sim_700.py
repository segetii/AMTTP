"""
v58 Stability Patch — $700 Simulation
======================================
Champion config : v58_tight  (asymmetric clamp lo=-0.01 + EMA span=3)
Capital         : $700 starting
Fees            : Maker orders  — 2 bps fee + 1 bps slippage = 3 bps / side
                  Cost charged per roundtrip (entry + exit transition in fired[])
Test window     : 2023-01-01 → present  (OOS from v58 stability patch)
OOS split       : first half  2023-2024  |  second half  2025-2026

Output sections
  1. Champion stats (Sharpe, CAGR, MaxDD, Sortino, Calmar, WinRate, PF)
  2. Quarterly breakdown   — compounding equity from $700
  3. Year-on-year summary  — annual return, start/end capital, profit
  4. Gross vs Net comparison  (cost drag diagnostic)

Results saved to  crypto_bsdt_v58_sim_700.json  in the same directory.
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
# Support both Windows dev environment and Linux CI/sandbox
# SCRIPT_DIR = .../research/adaptive-friction/pipeline/results
# parents[1] = .../research/adaptive-friction  (where collapse_geometry package lives)
_af_root = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(_af_root))
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')

# ── import champion-config building blocks from v58 ───────────────────────────
from run_crypto_pairs_v58_stability_patch import (
    _realized_vol, _dynamic_gth,
    CLIP, GH_TH, GH_TL, GL_TH, GL_TL,
    N_OPT, T_THRESH_BASE, G_THRESH_BASE, G_BOOST_THRESH, CHAMPION_BOOST,
    A_FIRE_THRESH, K_G, OOS_SPLIT,
    _make_cached_fetch,
    _cached_fetch_and_prepare, _cached_add_cross_market,
    _cached_fetch_binance_funding,
)

# ── import full pipeline from v63 (provides _full_stats) ─────────────────────
from run_crypto_pairs_v63_clip_boost import (
    _full_stats, ANN_1H,
    CALIB_BARS, BPD, PCA_K_B, FIRE_PERCENTILE,
    MasterOperator,
    build_1h_df, build_intraday_state_panel, calibrate_intraday_engine,
    compute_intraday_signals, compute_price_prediction_signals,
    compute_lambda_features, calibrate_channel_means,
    calibrate_firing_thresholds, compute_four_channel_signals_v39b,
    compute_1h_strategies, compute_quality, assemble_combined,
    add_leverage_features, build_daily_positions, upsample_daily_to_1h_pnl,
)

import run_crypto_pairs_v34_full_combined as _v34mod
from run_crypto_pairs_v34_full_combined import (
    OUT_DIR, TEST_START, TRAIN_START, TRAIN_END,
)

OUT_DIR_ = Path(OUT_DIR)

# ── simulation parameters ─────────────────────────────────────────────────────
START_CAPITAL : float = 700.0        # USD
FEE_BPS       : float = 2.0          # exchange maker fee  (bps per side)
SLIP_BPS      : float = 1.0          # slippage estimate   (bps per side)
COST_PER_SIDE : float = (FEE_BPS + SLIP_BPS) / 10_000.0

# v58 champion config
EMA_SPAN      : int   = 3
CLAMP_LO      : float = -0.01


# ── extended _build_pnl that also returns the fired mask ──────────────────────
def _build_pnl_with_fired(
    base:    pd.Series,
    sv36:    pd.DataFrame,
    lf:      pd.DataFrame,
    s4:      pd.DataFrame,
    rv_norm: pd.Series,
    lo:      float,
) -> tuple[pd.Series, pd.Series]:
    """Return (pnl, fired_series) — fired is the boolean execution signal."""
    idx  = base.index
    sv36 = sv36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lf.reindex(idx,   method='ffill').fillna(0.5)
    s4   = s4.reindex(idx,   method='ffill').fillna(0.0)
    gam  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lp   = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size = np.clip(1.0 - gam, 0.0, 1.0) * (0.75 + 0.5 * lp)

    gth   = _dynamic_gth(rv_norm.reindex(idx, method='ffill').fillna(1.0), lo)
    a_G   = s4['a_G']; a_A = s4['a_A']; a_T = s4['a_T']
    G_mem = a_G.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    T_mem = a_T.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    fired = a_A.shift(1).fillna(0.0) > A_FIRE_THRESH          # execution gate

    q_GH_TH = (fired & (G_mem > gth)  & (T_mem > T_THRESH_BASE)).astype(float)
    q_GH_TL = (fired & (G_mem > gth)  & (T_mem <= T_THRESH_BASE)).astype(float)
    q_GL_TH = (fired & (G_mem <= gth) & (T_mem > T_THRESH_BASE)).astype(float)
    q_GL_TL = (fired & (G_mem <= gth) & (T_mem <= T_THRESH_BASE)).astype(float)

    phase  = (1.0 + GH_TH*q_GH_TH + GH_TL*q_GH_TL
                  + GL_TH*q_GL_TH + GL_TL*q_GL_TL).clip(0.05, CLIP)
    flag   = (a_G.shift(1).fillna(0.0) > G_BOOST_THRESH).astype(float)
    pnl    = base.fillna(0.0) * size * (1.0 + CHAMPION_BOOST * flag) * phase
    return pnl, fired.astype(float)


def _apply_maker_fees(pnl: pd.Series, fired: pd.Series) -> pd.Series:
    """
    Deduct maker-order cost on each roundtrip entry/exit transition.
    A roundtrip = one entry + one exit = 2 side-transitions × COST_PER_SIDE.
    """
    transitions = fired.diff().abs().fillna(0).astype(bool)
    cost_series = transitions.astype(float) * COST_PER_SIDE
    return pnl - cost_series


def _rt_per_year(fired: pd.Series) -> float:
    """Count annualised roundtrips from the fired series."""
    n_transitions = int(fired.diff().abs().fillna(0).sum())
    n_rt  = n_transitions / 2.0
    yrs   = max((fired.index[-1] - fired.index[0]).total_seconds() / (365.25 * 86400), 0.01)
    return float(n_rt / yrs)


def _quarterly_breakdown(pnl_net: pd.Series, start_cap: float) -> pd.DataFrame:
    """Compound equity quarter by quarter from start_cap."""
    try:
        q_ret = (1.0 + pnl_net).resample('QE').prod() - 1.0
    except Exception:
        q_ret = (1.0 + pnl_net).resample('Q').prod() - 1.0

    rows = []; cap = start_cap
    for dt, r in q_ret.items():
        cap_end = cap * (1.0 + float(r))
        rows.append({
            'Quarter'     : f"{dt.year} Q{(dt.month-1)//3+1}",
            'Return'      : float(r),
            'Profit'      : float(cap_end - cap),
            'Start Capital': float(cap),
            'End Capital' : float(cap_end),
        })
        cap = cap_end
    return pd.DataFrame(rows)


def _yoy_breakdown(pnl_net: pd.Series, start_cap: float, test_start: str) -> list[dict]:
    """Compound equity year by year from start_cap for OOS years."""
    start_yr = int(test_start[:4])
    cap = start_cap
    rows = []
    for yr in sorted(pnl_net.index.year.unique()):
        if yr < start_yr:
            continue
        mask  = pnl_net.index.year == yr
        r     = float((1.0 + pnl_net[mask]).prod() - 1.0)
        cap_end = cap * (1.0 + r)
        rows.append({
            'Year'         : int(yr),
            'Return'       : float(r),
            'Start Capital': float(cap),
            'End Capital'  : float(cap_end),
            'Profit'       : float(cap_end - cap),
        })
        cap = cap_end
    return rows


# ═════════════════════════════════════════════════════════════════════════════
def main() -> dict:
    t0  = time.time()
    BAR = '=' * 100
    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)

    print(BAR)
    print(f"  v58 Stability Patch — $700 SIMULATION")
    print(f"  Champion : v58_tight  (lo={CLAMP_LO}, EMA span={EMA_SPAN})")
    print(f"  Capital  : ${START_CAPITAL:,.0f}  |  Fees: Maker {FEE_BPS:.0f} bps + slip {SLIP_BPS:.0f} bps = {FEE_BPS+SLIP_BPS:.0f} bps/side")
    print(BAR)

    tick = lambda msg: print(f'\n{msg}', flush=True)

    # ── data + signal pipeline (identical to v58/v65) ─────────────────────────
    tick('[1] 1h data')
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_mask   = df_1h.index >= TEST_START
    train_1h    = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    first_half  = (df_1h.index >= TEST_START) & (df_1h.index < OOS_SPLIT)
    second_half = df_1h.index >= OOS_SPLIT

    tick(f'[2] Funding  t={time.time()-t0:.0f}s')
    try:
        fund     = _cached_fetch_binance_funding()
        fund_eth = fund.get('ETHUSDT')
        fund_btc = fund.get('BTCUSDT')
    except Exception as e:
        print(f'    Warning: {e}'); fund_eth = fund_btc = None

    tick(f'[3] State panel  t={time.time()-t0:.0f}s')
    X = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X = np.nan_to_num(X)
    train_idx  = np.where(train_1h)[0]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[train_idx[-CALIB_BARS:]] = True

    tick(f'[4] Engine  t={time.time()-t0:.0f}s')
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(X, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)
    M_k1    = MasterOperator.calibrate(X[calib_mask], k=PCA_K_B)

    tick(f'[5] Signals  t={time.time()-t0:.0f}s')
    sig_v36       = compute_intraday_signals(X, df_1h, M, net, ews, stoch, e_star, theta)
    sig_v37, _, _ = compute_price_prediction_signals(X, df_1h, M, sig_v36, e_star, sigma_n)
    lam_feat      = compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))

    tick(f'[6] 4-channel  t={time.time()-t0:.0f}s')
    mu_norm  = calibrate_channel_means(X, calib_mask, M_k1)
    fire_thr = calibrate_firing_thresholds(X, calib_mask, M_k1, pct=FIRE_PERCENTILE)
    sig_4ch  = compute_four_channel_signals_v39b(X, df_1h, M_k1, sig_v36, fire_thr, mu_norm)

    tick(f'[7] Base portfolio  t={time.time()-t0:.0f}s')
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

    # ── v58 champion: rv EMA=3, clamp lo=-0.01 ───────────────────────────────
    tick(f'[8] Champion v58_tight  t={time.time()-t0:.0f}s')
    rv_ema       = _realized_vol(df_1h, ema_span=EMA_SPAN)
    pnl_gross, fired_all = _build_pnl_with_fired(
        base_pnl, sig_v36, lam_feat, sig_4ch, rv_ema, lo=CLAMP_LO)

    # Restrict to OOS test window
    pnl_gross_oos = pnl_gross[test_mask]
    fired_oos     = fired_all[test_mask]

    pnl_net_oos   = _apply_maker_fees(pnl_gross_oos, fired_oos)
    rt_yr         = _rt_per_year(fired_oos)
    annual_drag   = rt_yr * 2 * (FEE_BPS + SLIP_BPS) / 100.0   # fraction

    st_gross = _full_stats(pnl_gross_oos)
    st_net   = _full_stats(pnl_net_oos)

    # ── SECTION 1: champion stats ─────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  SECTION 1 — CHAMPION v58_tight STATS  (OOS: 2023-present)')
    print(f'{BAR}')
    print(f"\n  {'Metric':<22} {'Gross (pre-fee)':>18} {'Net (after maker fees)':>22}")
    print(f"  {'-'*22} {'-'*18} {'-'*22}")
    metrics = [
        ('Sharpe',   f'{st_gross["sharpe"]:>+15.4f}',  f'{st_net["sharpe"]:>+19.4f}'),
        ('Sortino',  f'{st_gross["sortino"]:>+15.4f}', f'{st_net["sortino"]:>+19.4f}'),
        ('Calmar',   f'{st_gross["calmar"]:>+15.4f}',  f'{st_net["calmar"]:>+19.4f}'),
        ('CAGR',     f'{st_gross["cagr"]:>+14.2%}',    f'{st_net["cagr"]:>+18.2%}'),
        ('Max DD',   f'{st_gross["max_dd"]:>+14.2%}',  f'{st_net["max_dd"]:>+18.2%}'),
        ('Win Rate', f'{st_gross["win_rate"]:>+14.2%}', f'{st_net["win_rate"]:>+18.2%}'),
        ('Profit F', f'{st_gross["profit_f"]:>+15.3f}', f'{st_net["profit_f"]:>+19.3f}'),
    ]
    for name, g, n in metrics:
        print(f"  {name:<22} {g} {n}")
    print(f"\n  Roundtrips/year : {rt_yr:.1f}  |  Fee per RT : {(FEE_BPS+SLIP_BPS)*2:.0f} bps"
          f"  |  Annual drag : {annual_drag:+.2%}")

    # OOS split breakdown
    pnl_net_h1 = _apply_maker_fees(pnl_gross[first_half],  fired_all[first_half])
    pnl_net_h2 = _apply_maker_fees(pnl_gross[second_half], fired_all[second_half])
    st_h1 = _full_stats(pnl_net_h1)
    st_h2 = _full_stats(pnl_net_h2)
    print(f"\n  OOS split (net):")
    print(f"    First half  (2023-2024) : Sharpe {st_h1['sharpe']:>+7.4f}  CAGR {st_h1['cagr']:>+7.2%}  MaxDD {st_h1['max_dd']:>+7.2%}")
    print(f"    Second half (2025-2026) : Sharpe {st_h2['sharpe']:>+7.4f}  CAGR {st_h2['cagr']:>+7.2%}  MaxDD {st_h2['max_dd']:>+7.2%}")

    # ── SECTION 2: quarterly breakdown ───────────────────────────────────────
    df_q = _quarterly_breakdown(pnl_net_oos, START_CAPITAL)
    print(f'\n{BAR}')
    print(f'  SECTION 2 — QUARTERLY BREAKDOWN  (${START_CAPITAL:,.0f} starting, maker fees)')
    print(f'{BAR}')
    print(f"\n  {'Quarter':<12} {'Return':>8}  {'Profit (USD)':>13}  {'Running Capital':>16}")
    print(f"  {'-'*12} {'-'*8}  {'-'*13}  {'-'*16}")
    for _, row in df_q.iterrows():
        p = row['Profit']; c = row['End Capital']
        sign = '+' if p >= 0 else ''
        print(f"  {row['Quarter']:<12} {row['Return']:>+8.2%}  {sign}{p:>10.2f} USD  ${c:>13.2f}")

    # ── SECTION 3: year-on-year summary ──────────────────────────────────────
    yoy_rows = _yoy_breakdown(pnl_net_oos, START_CAPITAL, TEST_START)
    print(f'\n{BAR}')
    print(f'  SECTION 3 — YEAR-ON-YEAR SUMMARY  (${START_CAPITAL:,.0f} starting, maker fees)')
    print(f'{BAR}')
    print(f"\n  {'Year':<7} {'Return':>8}  {'Start Capital':>15}  {'End Capital':>15}  {'Profit (USD)':>14}")
    print(f"  {'-'*7} {'-'*8}  {'-'*15}  {'-'*15}  {'-'*14}")
    for row in yoy_rows:
        ytd = ' (YTD)' if row['Year'] == yoy_rows[-1]['Year'] else ''
        sign = '+' if row['Profit'] >= 0 else ''
        print(f"  {row['Year']:<7} {row['Return']:>+8.2%}  ${row['Start Capital']:>13,.2f}  ${row['End Capital']:>13,.2f}  {sign}{row['Profit']:>+12.2f}{ytd}")

    final_cap = yoy_rows[-1]['End Capital'] if yoy_rows else START_CAPITAL
    total_profit = final_cap - START_CAPITAL
    cagr_net = st_net['cagr']
    cagr_gross = st_gross['cagr']

    print(f'\n  ┌{"─"*72}┐')
    print(f'  │  ${START_CAPITAL:,.0f} → ${final_cap:,.2f}   (total profit: ${total_profit:>+,.2f}){"":>18}│')
    print(f'  │  Gross CAGR {cagr_gross:>+.1%}  →  Net CAGR {cagr_net:>+.1%}  (drag {annual_drag:>+.2%}/yr){"":>19}│')
    print(f'  │  Net Sharpe {st_net["sharpe"]:>+.4f}   Calmar {st_net["calmar"]:>+.3f}   MaxDD {st_net["max_dd"]:>+.2%}{"":>21}│')
    print(f'  │  Maker fee {FEE_BPS:.0f} bps + slip {SLIP_BPS:.0f} bps = {FEE_BPS+SLIP_BPS:.0f} bps/side   RT/yr ≈ {rt_yr:.0f}{"":>25}│')
    print(f'  └{"─"*72}┘')
    print(f'\n{BAR}')

    # ── save ─────────────────────────────────────────────────────────────────
    class _NpEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, np.integer):  return int(obj)
            if isinstance(obj, np.floating): return float(obj)
            if isinstance(obj, np.bool_):    return bool(obj)
            if isinstance(obj, np.ndarray):  return obj.tolist()
            return super().default(obj)

    out = {
        'version'      : 'v58_sim_700',
        'champion'     : 'v58_tight (lo=-0.01, EMA=3)',
        'start_capital': START_CAPITAL,
        'fee_bps'      : FEE_BPS,
        'slip_bps'     : SLIP_BPS,
        'rt_per_year'  : float(rt_yr),
        'annual_drag'  : float(annual_drag),
        'gross_stats'  : {k: float(v) if not isinstance(v, dict)
                          else {str(kk): float(vv) for kk, vv in v.items()}
                          for k, v in st_gross.items()},
        'net_stats'    : {k: float(v) if not isinstance(v, dict)
                          else {str(kk): float(vv) for kk, vv in v.items()}
                          for k, v in st_net.items()},
        'quarterly'    : df_q.to_dict('records'),
        'yoy'          : yoy_rows,
        'final_capital': float(final_cap),
        'total_profit' : float(total_profit),
        'elapsed_s'    : float(time.time() - t0),
    }
    out_path = OUT_DIR_ / 'crypto_bsdt_v58_sim_700.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(out, f, indent=2, cls=_NpEncoder)
    print(f'  Results saved → {out_path}')
    print(f'  Total elapsed : {time.time()-t0:.1f}s')
    print(BAR)
    return out


if __name__ == '__main__':
    main()
