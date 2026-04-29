"""
Crypto BSDT v68 — Paper-Correct v58 Signal Interpretation
===========================================================
Model: v58_tight  (FROZEN)

Diagnosis of v66/v67 signal error
-----------------------------------
v66/v67 applied the BSDT phase modulator to the multi-strategy BASE PORTFOLIO,
which includes:
  H3  ETH-BTC spread  (sign(3d_spread_mom) × (ret_eth − ret_btc)) — PAIRS: 2 legs
  H4  macro dominance (pos_macro × ret_btc + (−pos_macro) × ret_eth)  — PAIRS: 2 legs
This caused the "selling both long and short" problem: fee counts were ambiguous
(1-leg vs 1.5-leg vs 2-leg debate in v66/v67).

Paper-Correct v58 (§29.4, §28.11 of math_reference):
------------------------------------------------------
The engine emits ONE directional signal per bar:
  sign(M_t) = sign(Σ_i r̃_i)   — return deviation sum, §28.13

Position sizing (§28.11, v58 production spec):
  size_t = size_base × (1 − γ*_{t−1}) × λ_t^price × 𝟙[λ̇_t^price ≥ 0]
         = sig_v37['size_v37'] (already computed with all three factors)

Full PnL formula (§29.4):
  PnL_t = sign(M_{t−1}) × ret_eth[t]
         × size_v37[t−1]
         × (1 + c_b · 𝟙[a_G(t−1) > θ_GBT])   [G-boost]
         × ϕ_t                                  [phase: 6.0 / 0.05 / 1.0]

This is a SINGLE INSTRUMENT (ETH) SINGLE DIRECTION trade. Fee = K × 1 leg × 3 bps/side.
The base portfolio multi-strategy decomposition is NOT how the engine signals are used.

Sections
--------
  0. Signal Profile  — move_dir, lambda_price, size_v37 statistics
  1. Gross Comparison — v58_paper (sign(M_t)) vs v58_code (base portfolio)
  2. Net Fee Sweep    — K=1/2/3/5 with honest 1-leg maker fees
  3. $700 Quarterly Projection  (K=1/2/3/5)
  4. Entry/Exit Signal Distribution
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
from run_crypto_pairs_v67_pairs_fee import (
    _count_rt, _compute_phase_states,
    _apply_leverage, _quarterly_projection,
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
FEE_SIDE_BPS   = MAKER_FEE_BPS + MAKER_SLIP_BPS   # 3 bps per side, 1 leg
BORROW_BPS_PA  = 500                               # 5% p.a.
LEVERAGE_LEVELS = [1.0, 2.0, 3.0, 5.0]
START_CAPITAL   = 700.0
LO              = -0.01


# ── Paper-correct v58 PnL builder ─────────────────────────────────────────────

def _build_pnl_v58_paper(sig_v37: pd.DataFrame,
                          sig_4ch: pd.DataFrame,
                          rv_norm: pd.Series,
                          df_1h:   pd.DataFrame,
                          lo:      float = -0.01) -> pd.Series:
    """
    Paper-correct v58 (§29.4, §28.11):
      PnL_t = sign(M_{t-1}) × ret_eth[t]
             × size_v37[t-1]
             × (1 + CHAMPION_BOOST × 𝟙[a_G(t-1) > G_BOOST_THRESH])
             × ϕ_t

    sign(M_t)  = sig_v37['move_dir']          — single directional signal
    size_v37   = sig_v37['size_v37']           — (1-γ*)×λ^price×𝟙[dλ≥0]
    ϕ_t        = 4-quadrant phase (6/0.05/1.0) — same as v58_code
    """
    idx = sig_4ch.index

    # Direction: sign(M_t), shift 1 bar (bar t−1 signal → bar t return)
    move_dir = sig_v37['move_dir'].reindex(idx, method='ffill').shift(1).fillna(0.0)

    # Size: already encodes (1-γ*)×λ^price×𝟙[dλ≥0], shift 1 bar
    size = sig_v37['size_v37'].reindex(idx, method='ffill').shift(1).fillna(0.0)

    # G-boost
    flag = (sig_4ch['a_G'].shift(1).fillna(0.0) > G_BOOST_THRESH).astype(float)
    g_boost = 1.0 + CHAMPION_BOOST * flag

    # Phase (identical to _build_pnl_v58)
    a_G   = sig_4ch['a_G'];  a_A = sig_4ch['a_A'];  a_T = sig_4ch['a_T']
    G_mem = a_G.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    T_mem = a_T.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    fired = a_A.shift(1).fillna(0.0) > A_FIRE_THRESH
    gth   = _dynamic_gth(rv_norm.reindex(idx, method='ffill').fillna(1.0), lo)
    q_GH_TH = (fired & (G_mem > gth)  & (T_mem > T_THRESH_BASE)).astype(float)
    q_GH_TL = (fired & (G_mem > gth)  & (T_mem <= T_THRESH_BASE)).astype(float)
    q_GL_TH = (fired & (G_mem <= gth) & (T_mem > T_THRESH_BASE)).astype(float)
    q_GL_TL = (fired & (G_mem <= gth) & (T_mem <= T_THRESH_BASE)).astype(float)
    phase   = (1.0 + GH_TH*q_GH_TH + GH_TL*q_GH_TL
                   + GL_TH*q_GL_TH + GL_TL*q_GL_TL).clip(0.05, CLIP)

    # PnL on ETH — 1 leg, single direction
    ret_eth = df_1h['ret_eth'].reindex(idx, fill_value=0.0)
    pnl = move_dir * ret_eth * size * g_boost * phase
    return pnl.fillna(0.0)


def _apply_cost_1leg(pnl: pd.Series, fired: np.ndarray,
                     fee_bps: float, slip_bps: float, K: float) -> pd.Series:
    """Single-leg fee: K × 1 × (fee+slip) bps per transition."""
    events = pd.Series(fired.astype(int), index=pnl.index).diff().abs().fillna(0).astype(bool)
    cost   = K * 1.0 * (fee_bps + slip_bps) / 10_000.0
    return pnl - events.astype(float) * cost


def _quarterly_proj(pnl: pd.Series, start_cap: float) -> list:
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
    print('  v68 - Paper-Correct v58 Signal  (sign(M_t) = single directional, ETH, 1-leg fee)')
    print('  Engine: v58_tight FROZEN | Direction: move_dir from sig_v37 | Fee: K×1×3bps/side')
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

    # Verify sig_v37 has the columns we need
    print(f'\n  sig_v37 columns: {list(sig_v37.columns)}')
    has_size_v37   = 'size_v37'   in sig_v37.columns
    has_move_dir   = 'move_dir'   in sig_v37.columns
    has_lambda_prc = 'lambda_price' in sig_v37.columns
    print(f'  move_dir:   {"YES" if has_move_dir else "MISSING — will use sign(ret_eth rolling)"}')
    print(f'  size_v37:   {"YES" if has_size_v37 else "MISSING — will use fallback from v58_code"}')
    print(f'  lambda_price: {"YES" if has_lambda_prc else "MISSING"}')

    t(f'[6] 4-channel  t={time.time()-t0:.0f}s')
    mu_norm  = calibrate_channel_means(X, calib_mask, M_k1)
    fire_thr = calibrate_firing_thresholds(X, calib_mask, M_k1, pct=FIRE_PERCENTILE)
    sig_4ch  = compute_four_channel_signals_v39b(X, df_1h, M_k1, sig_v36, fire_thr, mu_norm)

    t(f'[7] Base portfolio (v58_code reference)  t={time.time()-t0:.0f}s')
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

    t(f'[8] v58_code PnL (proxy reference)  t={time.time()-t0:.0f}s')
    pnl_code = _build_pnl_v58(base_pnl, sig_v36, lam_feat, sig_4ch, rv_ema, LO)

    t(f'[9] v58_paper PnL (sign(M_t), ETH, 1-leg)  t={time.time()-t0:.0f}s')

    # Fallback: if size_v37 missing, reconstruct from components
    if not has_size_v37:
        print('  [!] size_v37 missing — reconstructing from gam + lambda_price')
        gam_full = sig_v36['gamma_star_adj'].shift(1).fillna(0.24) if 'gamma_star_adj' in sig_v36.columns else pd.Series(0.24, index=sig_v37.index)
        lp_full  = sig_v37['lambda_price'] if has_lambda_prc else pd.Series(0.5, index=sig_v37.index)
        # dlambda_dt: approximate derivative of lambda_price
        dlam     = lp_full.diff().fillna(0.0)
        size_v37_series = np.clip(1.0 - gam_full, 0.0, 1.0) * lp_full * (dlam >= 0).astype(float)
        sig_v37 = sig_v37.copy()
        sig_v37['size_v37'] = size_v37_series

    if not has_move_dir:
        print('  [!] move_dir missing — using sign of return deviation sum from sig_v36')
        # Approximate: sign of short-run ETH return
        sig_v37 = sig_v37.copy()
        sig_v37['move_dir'] = np.sign(df_1h['ret_eth'].rolling(3, min_periods=1).sum().reindex(sig_v37.index))

    pnl_paper = _build_pnl_v58_paper(sig_v37, sig_4ch, rv_ema, df_1h, lo=LO)

    # Phase states for fired mask
    phase_full, q_GH_TH_full, q_sup_full, fired_full = \
        _compute_phase_states(sig_4ch, rv_ema, lo=LO)

    # OOS slice
    pnl_code_oos  = pnl_code[test_mask]
    pnl_paper_oos = pnl_paper[test_mask]
    fired_oos     = fired_full[test_mask]
    test_idx      = df_1h.index[test_mask]

    rt = _count_rt(fired_oos.values, test_idx)

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 0 — Signal Profile
    # ══════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print('  SECTION 0 — v58 Paper Signal Profile (OOS)')
    print(BAR)

    mv_oos   = sig_v37['move_dir'].reindex(df_1h.index[test_mask]).fillna(0.0)
    sz_oos   = sig_v37['size_v37'].reindex(df_1h.index[test_mask]).fillna(0.0)
    lp_oos   = sig_v37['lambda_price'].reindex(df_1h.index[test_mask]).fillna(0.0) if has_lambda_prc else pd.Series(np.nan, index=test_idx)

    n_long   = int((mv_oos > 0).sum())
    n_short  = int((mv_oos < 0).sum())
    n_flat   = int((mv_oos == 0).sum())

    print(f"""
  move_dir (sign(M_t)):
    Long  (+1): {n_long:,} bars  ({n_long/len(mv_oos)*100:.1f}%)
    Short (−1): {n_short:,} bars  ({n_short/len(mv_oos)*100:.1f}%)
    Flat  ( 0): {n_flat:,} bars  ({n_flat/len(mv_oos)*100:.1f}%)

  size_v37 = (1−γ*)×λ^price×𝟙[dλ≥0]:
    Mean: {sz_oos.mean():.4f}   Std: {sz_oos.std():.4f}
    Zero (dλ < 0, no entry): {(sz_oos == 0).sum():,} bars
    Active (size > 0):  {(sz_oos > 0).sum():,} bars

  lambda_price (energy in price dim):
    Mean:  {lp_oos.mean():.3f}   >0.5: {(lp_oos > 0.5).sum():,} bars ({(lp_oos > 0.5).sum()/len(lp_oos)*100:.1f}%)

  Fired events (a_A > thresh): {int(fired_oos.sum()):,} bars = {rt['rt_pa']:.0f} RT/yr
  Fee model: K × 1 leg × {FEE_SIDE_BPS:.0f} bps/side per RT (no pairs ambiguity)
""")

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 1 — Gross Comparison: paper vs code
    # ══════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print('  SECTION 1 — Gross Comparison: v58_paper (sign(M_t)) vs v58_code (base portfolio)')
    print(BAR)

    sp = _full_stats(pnl_paper_oos)
    sc = _full_stats(pnl_code_oos)

    print(f"""
  {'Metric':<20}  {'v58_paper':>12}  {'v58_code':>12}  {'Delta':>10}
  {'-'*58}
  {'Sharpe':<20}  {sp['sharpe']:>+12.3f}  {sc['sharpe']:>+12.3f}  {sp['sharpe']-sc['sharpe']:>+10.3f}
  {'Sortino':<20}  {sp['sortino']:>+12.3f}  {sc['sortino']:>+12.3f}  {sp['sortino']-sc['sortino']:>+10.3f}
  {'CAGR':<20}  {sp['cagr']*100:>+11.2f}%  {sc['cagr']*100:>+11.2f}%  {(sp['cagr']-sc['cagr'])*100:>+9.2f}%
  {'MaxDD':<20}  {sp['max_dd']*100:>+11.2f}%  {sc['max_dd']*100:>+11.2f}%  {(sp['max_dd']-sc['max_dd'])*100:>+9.2f}%
  {'Calmar':<20}  {sp['calmar']:>+12.3f}  {sc['calmar']:>+12.3f}  {sp['calmar']-sc['calmar']:>+10.3f}
  {'WinRate':<20}  {sp['win_rate']:>+12.3f}  {sc['win_rate']:>+12.3f}
  YoY paper : {" | ".join(f"{yr}: {r*100:+.1f}%" for yr, r in sp['yoy'].items())}
  YoY code  : {" | ".join(f"{yr}: {r*100:+.1f}%" for yr, r in sc['yoy'].items())}

  Signal clarity: paper uses single instrument (ETH) + sign(M_t)
                  code  uses quality-weighted multi-strategy portfolio
""")

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 2 — Net Fee Sweep (1-leg, paper-correct)
    # ══════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print(f'  SECTION 2 — Net Fee Sweep (1-leg, {FEE_SIDE_BPS:.0f} bps/side, {BORROW_BPS_PA/100:.0f}% borrow)')
    print(f'  Model: v58_paper | sign(M_t) × ETH | 1 leg (no pairs ambiguity)')
    print(BAR)

    hdr = (f"  {'K':>4}  {'Gross':>8}  {'Net CAGR':>9}  {'Net Sharpe':>11}"
           f"  {'MaxDD':>8}  {'Fee Drag':>9}  {'$700→':>10}")
    print(hdr)
    print('  ' + '-' * 80)

    paper_results: dict = {}
    for K in LEVERAGE_LEVELS:
        pnl_lev = _apply_leverage(pnl_paper_oos, K)
        pnl_net = _apply_cost_1leg(pnl_lev, fired_oos.values,
                                   MAKER_FEE_BPS, MAKER_SLIP_BPS, K)
        sg  = _full_stats(pnl_lev)
        sn  = _full_stats(pnl_net)
        drag = K * rt['rt_pa'] * 2 * 1.0 * FEE_SIDE_BPS / 10_000 * 100
        paper_results[K] = {'stats': sn, 'pnl': pnl_net}
        star = ' <--' if K == 2.0 else ''
        print(f"  {K:>4.1f}  {sg['cagr']*100:>+7.2f}%  "
              f"{sn['cagr']*100:>+8.2f}%  {sn['sharpe']:>+10.3f}"
              f"  {sn['max_dd']*100:>+7.2f}%  {drag:>+8.1f}%"
              f"  ${sn['final'] * START_CAPITAL / 100:>9,.2f}{star}")

    print(f"""
  Annual fee drag = K × {rt['rt_pa']:.0f} RT/yr × 2 sides × 1 leg × {FEE_SIDE_BPS:.0f} bps
  At K=1: {1*rt['rt_pa']*2*1*FEE_SIDE_BPS/10_000*100:.1f}%   K=2: {2*rt['rt_pa']*2*1*FEE_SIDE_BPS/10_000*100:.1f}%   K=5: {5*rt['rt_pa']*2*1*FEE_SIDE_BPS/10_000*100:.1f}%
  1-leg fee is correct because sign(M_t) drives a SINGLE ETH position.
""")

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 3 — $700 Quarterly Projection
    # ══════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print(f'  SECTION 3 — ${START_CAPITAL:.0f} Quarterly Projection  (v58_paper, 1-leg net)')
    print(BAR)

    for K in LEVERAGE_LEVELS:
        rows = _quarterly_proj(paper_results[K]['pnl'], START_CAPITAL)
        sn   = paper_results[K]['stats']
        print(f'\n  -- K={K:.0f}  Net CAGR {sn["cagr"]*100:+.2f}%  '
              f'Sharpe {sn["sharpe"]:+.3f}  MaxDD {sn["max_dd"]*100:.2f}%')
        print(f'  {"Quarter":<12}  {"Return":>10}  {"Capital":>12}')
        print('  ' + '-' * 38)
        for row in rows:
            print(f'  {row["Quarter"]:<12}  {row["Return"]:>10}  {row["Capital"]:>12}')

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 4 — Entry Signal Distribution: when does sign(M_t) fire?
    # ══════════════════════════════════════════════════════════════════════════
    print(f'\n{BAR}')
    print('  SECTION 4 — When Paper Signal Fires (GH_TH + sign(M_t) alignment)')
    print(BAR)

    # align all on test_idx for safe boolean ops
    gh_arr  = (phase_full[test_mask].values >= 5.9)
    mv_arr  = mv_oos.reindex(test_idx).fillna(0.0).values
    pnl_arr = pnl_paper_oos.values

    long_gh  = int((gh_arr & (mv_arr > 0)).sum())
    short_gh = int((gh_arr & (mv_arr < 0)).sum())
    flat_gh  = int((gh_arr & (mv_arr == 0)).sum())
    n_gh     = int(gh_arr.sum())

    long_pnl  = float(pnl_arr[gh_arr & (mv_arr > 0)].sum() * 100)
    short_pnl = float(pnl_arr[gh_arr & (mv_arr < 0)].sum() * 100)

    print(f"""
  When GH_TH is active (ϕ=6, {n_gh} bars):
    sign(M_t) = LONG  (+1): {long_gh} bars  ({long_gh/max(n_gh,1)*100:.1f}%)
    sign(M_t) = SHORT (−1): {short_gh} bars  ({short_gh/max(n_gh,1)*100:.1f}%)
    sign(M_t) = FLAT  ( 0): {flat_gh} bars  ({flat_gh/max(n_gh,1)*100:.1f}%)

  Long vs Short balance at GH_TH: {"BALANCED" if abs(long_gh-short_gh)/max(n_gh,1) < 0.1 else "DIRECTIONAL BIAS"}
  Long PnL (GH_TH active):  {long_pnl:+.2f}% cumulative
  Short PnL (GH_TH active): {short_pnl:+.2f}% cumulative
""")

    # ── save ─────────────────────────────────────────────────────────────────
    def _flt(v):
        return float(v) if isinstance(v, (int, float, np.integer, np.floating)) else v

    save = {
        'version': 'v68',
        'signal_profile': {
            'n_long_bars': int(n_long), 'n_short_bars': int(n_short),
            'n_flat_bars': int(n_flat), 'rt_pa': float(rt['rt_pa']),
            'fee_model': '1-leg × 3bps/side (paper-correct)',
        },
        'gross_paper': {k: _flt(v) for k, v in sp.items() if k != 'yoy'},
        'gross_paper_yoy': {str(yr): float(r) for yr, r in sp['yoy'].items()},
        'gross_code': {k: _flt(v) for k, v in sc.items() if k != 'yoy'},
        'gross_code_yoy': {str(yr): float(r) for yr, r in sc['yoy'].items()},
        'net_1leg': {},
    }
    for K in LEVERAGE_LEVELS:
        s = paper_results[K]['stats']
        drag = K * rt['rt_pa'] * 2 * 1.0 * FEE_SIDE_BPS / 10_000 * 100
        save['net_1leg'][f'K{K}'] = {
            **{k: _flt(v) for k, v in s.items() if k != 'yoy'},
            'yoy': {str(yr): float(r) for yr, r in s['yoy'].items()},
            'drag_pct': float(drag),
        }

    out = OUT_DIR_ / 'crypto_bsdt_v68_results.json'
    with open(out, 'w') as f:
        json.dump(save, f, indent=2)
    print(f'\n  Saved: {out}')
    print(f'  Total runtime: {time.time()-t0:.0f}s')
    print(BAR)
