"""$1,000 capital simulation for current best combo.

Best combo from §26.10:
  pnl_combo = pnl_v58_full + (k*P_E7 + k*P_B1 + k*P_E6)/3
  k = 0.1050 (calibration-only vol match)

Cost models:
  realistic:
    - 5 bps fee + 2 bps slippage per round-trip
    - v58 core charged on active episodes (entry+exit = one round-trip)
    - geometry charged on sign flips / entries
    - funding drag = 1 bp/day per active notional
  conservative:
    - same fees/slippage/funding
    - v58 core charged every active hour (punitive)

Outputs quarterly and yearly P&L for $1,000.
"""
from __future__ import annotations
import sys, time, json, itertools
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')

from collapse_geometry import MasterOperator                            # noqa: E402
from run_crypto_pairs_v36_intraday_bsdt import (                        # noqa: E402
    CALIB_BARS, BPD,
    build_intraday_state_panel, calibrate_intraday_engine, _stats,
    compute_intraday_signals,
)
from run_crypto_pairs_v37_price_prediction import compute_price_prediction_signals  # noqa: E402
from run_crypto_pairs_v38_lambda_norm import compute_lambda_features              # noqa: E402
from run_crypto_pairs_v34_full_combined import (                        # noqa: E402
    build_1h_df, OUT_DIR, TEST_START, TRAIN_START, TRAIN_END,
    compute_1h_strategies, compute_quality, assemble_combined,
    upsample_daily_to_1h_pnl, build_daily_positions,
    add_leverage_features,
)
from run_crypto_pairs_v39_four_channels import (                        # noqa: E402
    FIRE_PERCENTILE, calibrate_firing_thresholds,
)
from run_crypto_pairs_v39b_k1_scaled import (                           # noqa: E402
    compute_four_channel_signals_v39b, calibrate_channel_means, PCA_K_B,
)
from run_robustness_validation import (                                  # noqa: E402
    _build_pnl, _apply_overlays, CORE,
    _make_cached_fetch, _cached_fetch_binance_funding,
    _cached_fetch_and_prepare, _cached_add_cross_market,
)
from corrected_diagnostics import compute_corrected_diagnostics, v58_dynamic_gth  # noqa: E402
import run_crypto_pairs_v34_full_combined as _v34mod                    # noqa: E402

CACHE_FG = Path(r'C:\amttp\data\geometric_extractor_engine_arrays_funded_v58_fg.npz')
INIT_CAPITAL = 1000.0
FEE_BPS_RT = 5.0
SLIP_BPS_RT = 2.0
FUNDING_BPS_PER_DAY = 1.0
LOW_FEE_BPS_RT = 1.5
LOW_SLIP_BPS_RT = 0.5
LOW_FUNDING_BPS_PER_DAY = 0.5
K_GRID = [1.0, 2.0, 3.0, 5.0]


def _metric_returns(r: pd.Series, init: float) -> dict:
    eq = init * (1.0 + r.fillna(0.0)).cumprod()
    peak = eq.cummax()
    dd = (eq - peak) / peak
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    cagr = (eq.iloc[-1] / init) ** (1.0 / years) - 1.0
    sh = float(np.sqrt(24*365.25) * r.mean() / r.std()) if r.std() > 0 else 0.0
    return dict(final=float(eq.iloc[-1]), profit=float(eq.iloc[-1] - init),
                profit_pct=float(eq.iloc[-1] / init - 1.0), cagr=float(cagr),
                sharpe=float(sh), maxdd=float(dd.min()), equity=eq)


def _period_table(eq: pd.Series, freq: str) -> list[dict]:
    rows = []
    groups = eq.groupby(pd.Grouper(freq=freq))
    for period, s in groups:
        if len(s) < 2:
            continue
        start = float(s.iloc[0])
        end = float(s.iloc[-1])
        rows.append(dict(period=str(period.date()), start=start, end=end,
                         profit=end-start, return_pct=end/start-1.0))
    return rows


def _turnover_roundtrips_from_pos(pos: pd.Series) -> pd.Series:
    """Round-trip units: flip +1->-1 = 1, entry/exit = 0.5."""
    p = pos.fillna(0.0).astype(float)
    return p.diff().abs().fillna(p.abs()) / 2.0


def main():
    BAR = '=' * 100
    print(BAR)
    print("  $1,000 SIMULATION — v58_full + E7/B1/E6 geometry basket")
    print(BAR)
    t0 = time.time()

    # ── rebuild official v58_full and extractors (uses caches heavily) ──
    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    fund = _cached_fetch_binance_funding()
    X = np.nan_to_num(build_intraday_state_panel(df_1h, fund.get('BTCUSDT'), fund.get('ETHUSDT')))
    idx = df_1h.index
    ret_eth = df_1h['ret_eth'].fillna(0.0)
    train_1h = (idx >= TRAIN_START) & (idx < TEST_START)
    train_idx = np.where(train_1h)[0]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[train_idx[-CALIB_BARS:]] = True
    test_mask = idx >= TEST_START

    print(f"\n[1] v58_full stack t={time.time()-t0:.0f}s", flush=True)
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(X, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)
    M_k1 = MasterOperator.calibrate(X[calib_mask], k=PCA_K_B)
    sig_v36 = compute_intraday_signals(X, df_1h, M, net, ews, stoch, e_star, theta)
    sig_v37, _, _ = compute_price_prediction_signals(X, df_1h, M, sig_v36, e_star, sigma_n)
    lam_feat = compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))
    mu_norm = calibrate_channel_means(X, calib_mask, M_k1)
    fire_thr = calibrate_firing_thresholds(X, calib_mask, M_k1, pct=FIRE_PERCENTILE)
    sig_4ch = compute_four_channel_signals_v39b(X, df_1h, M_k1, sig_v36, fire_thr, mu_norm)

    h_strats = compute_1h_strategies(df_1h, has_sol)
    df_d = _cached_fetch_and_prepare(); df_d = _cached_add_cross_market(df_d)
    fund_d = _cached_fetch_binance_funding(); df_d = add_leverage_features(df_d, fund_d)
    tmask_d = (df_d.index >= TRAIN_START) & (df_d.index <= TRAIN_END)
    pos_dict, _, _, gate_daily = build_daily_positions(df_d, tmask_d, np.asarray(tmask_d, dtype=bool))
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
    pnl_v58_dyn = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch,
                             CORE['clip'], CORE['tth'], CORE['aft'], CORE['cb'], CORE['gbt'], v58_dynamic_gth(df_1h))
    diag = compute_corrected_diagnostics(X, df_1h, M, lyap, start_idx=0, history_len=168,
                                         cache_key='v58_default', use_cache=True, verbose=True)
    pnl_v58_full = _apply_overlays(
        pnl_v58_dyn,
        cos=(diag['cos_theta'] > 0.0).astype(float),
        rho=(diag['rho_normalised'] > 0.5).astype(float),
        M=(diag['M_margin'] > 0.0).astype(float),
    ).reindex(idx).fillna(0.0)

    # ── geometry PnLs E7/B1/E6 ────────────────────────────────────────
    print(f"\n[2] geometry basket t={time.time()-t0:.0f}s", flush=True)
    z = np.load(CACHE_FG)
    F_all = z['F_all']; G_all = z['G_all']; valid = z['valid']
    T_total, N, d = X.shape
    F_flat = F_all.reshape(T_total, -1)
    G_flat = G_all.reshape(T_total, -1)
    Xt_flat = X.reshape(T_total, -1)
    dX = np.full_like(X, np.nan, dtype=np.float32); dX[:-1] = X[1:] - X[:-1]
    dX_flat = dX.reshape(T_total, -1)
    dX_prev = np.roll(dX_flat, 1, axis=0); dX_prev[0] = np.nan

    # E7
    alpha = 2.0 / (32 + 1)
    Fbar = np.full_like(F_flat, np.nan); Fbar[0] = F_flat[0]
    for t in range(1, T_total):
        if np.isnan(F_flat[t]).any(): Fbar[t] = Fbar[t-1]
        elif np.isnan(Fbar[t-1]).any(): Fbar[t] = F_flat[t]
        else: Fbar[t] = (1-alpha)*Fbar[t-1] + alpha*F_flat[t]
    sig_E7 = pd.Series(np.einsum('ti,ti->t', Fbar, dX_prev), index=idx)

    # B1
    sig_B1 = pd.Series(np.einsum('ti,ti->t', G_flat, dX_prev), index=idx)

    # E6
    Xc = Xt_flat[calib_mask]
    mu_calib = Xc.mean(axis=0)
    Sigma_inv = np.linalg.inv(np.cov(Xc, rowvar=False) + 1e-6*np.eye(N*d))
    e6 = np.full(T_total, np.nan, dtype=np.float64)
    for t in range(1, T_total):
        if valid[t]:
            try: e6[t] = float(-(F_flat[t] @ (Sigma_inv @ (Xt_flat[t] - mu_calib))))
            except Exception: pass
    sig_E6 = pd.Series(e6, index=idx)

    signals = {'E7': sig_E7, 'B1': sig_B1, 'E6': sig_E6}
    raw_pnls = {n: np.sign(s).shift(1).fillna(0.0) * ret_eth for n, s in signals.items()}
    positions = {n: np.sign(s).shift(1).fillna(0.0) for n, s in signals.items()}
    k = float(pnl_v58_full[calib_mask].std() / max(raw_pnls['E7'][calib_mask].std(), 1e-12))
    scaled = {n: k * raw_pnls[n] for n in raw_pnls}
    pnl_combo_gross = pnl_v58_full + (scaled['E7'] + scaled['B1'] + scaled['E6']) / 3.0

    # ── costs per K=1 return unit ─────────────────────────────────────
    active_core = (pnl_v58_full.abs() > 1e-12).astype(float)
    # Realistic: v58 entry/exit episodes cost half round-trip per transition.
    core_turnover_episode = active_core.diff().abs().fillna(active_core).astype(float) / 2.0
    # Conservative: full round-trip cost every active hour.
    core_turnover_active = active_core.astype(float)

    # Geometry turnover. Each component has notional scale k/3.
    geom_turnover = pd.Series(0.0, index=idx)
    geom_active_notional = pd.Series(0.0, index=idx)
    for n, pos in positions.items():
        scale = k / 3.0
        geom_turnover = geom_turnover + scale * _turnover_roundtrips_from_pos(pos)
        geom_active_notional = geom_active_notional + scale * (pos.abs() > 0).astype(float)

    # v58 active notional assumed 1 when active.
    def _cost_series(fee_bps_rt: float, slip_bps_rt: float, funding_bps_day: float,
                     *, conservative_core: bool) -> pd.Series:
        rt_cost = (fee_bps_rt + slip_bps_rt) / 1e4
        funding_hour = (funding_bps_day / 24.0) / 1e4
        core_turnover = core_turnover_active if conservative_core else core_turnover_episode
        return rt_cost * (core_turnover + geom_turnover) + funding_hour * (active_core + geom_active_notional)

    cost_gross = pd.Series(0.0, index=idx)
    cost_low = _cost_series(LOW_FEE_BPS_RT, LOW_SLIP_BPS_RT, LOW_FUNDING_BPS_PER_DAY,
                            conservative_core=False)
    cost_realistic = _cost_series(FEE_BPS_RT, SLIP_BPS_RT, FUNDING_BPS_PER_DAY,
                                  conservative_core=False)
    cost_conservative = _cost_series(FEE_BPS_RT, SLIP_BPS_RT, FUNDING_BPS_PER_DAY,
                                     conservative_core=True)

    # ── simulations ──────────────────────────────────────────────────
    print(f"\n{BAR}")
    print("  CAPITAL SIMULATION — $1,000 start, fees+slippage+funding")
    print(BAR)
    gross = pnl_combo_gross[test_mask].astype(float)
    cr = cost_realistic[test_mask].astype(float)
    cc = cost_conservative[test_mask].astype(float)

    summary = {}
    cl = cost_low[test_mask].astype(float)
    cg = cost_gross[test_mask].astype(float)
    cost_models = [
        ('gross_no_cost', cg, 0.0, 0.0, 0.0),
        ('low_cost_maker', cl, LOW_FEE_BPS_RT, LOW_SLIP_BPS_RT, LOW_FUNDING_BPS_PER_DAY),
        ('realistic_taker', cr, FEE_BPS_RT, SLIP_BPS_RT, FUNDING_BPS_PER_DAY),
        ('conservative', cc, FEE_BPS_RT, SLIP_BPS_RT, FUNDING_BPS_PER_DAY),
    ]

    for model_name, cost, fee_bps, slip_bps, fund_bps in cost_models:
        print(f"\n  Cost model: {model_name.upper()}  (fee {fee_bps:.1f}bp + slip {slip_bps:.1f}bp RT, funding {fund_bps:.1f}bp/day)")
        print(f"  {'K':>4} {'final $':>12} {'profit $':>12} {'profit %':>10} {'CAGR':>9} {'Sharpe':>8} {'MaxDD':>8} {'cost drag':>10}")
        print(f"  {'-'*4} {'-'*12} {'-'*12} {'-'*10} {'-'*9} {'-'*8} {'-'*8} {'-'*10}")
        summary[model_name] = {}
        for K in K_GRID:
            r_net = K * (gross - cost)
            # avoid impossible negative equity if too much leverage
            r_net = r_net.clip(lower=-0.95)
            m = _metric_returns(r_net, INIT_CAPITAL)
            drag = float((K * cost).sum() * INIT_CAPITAL)
            summary[model_name][str(K)] = {k0: v for k0, v in m.items() if k0 != 'equity'} | {'cost_drag_dollars': drag}
            summary[model_name][str(K)]['quarterly'] = _period_table(m['equity'], 'Q')
            summary[model_name][str(K)]['yearly'] = _period_table(m['equity'], 'Y')
            print(f"  {K:>4.1f} {m['final']:>12,.2f} {m['profit']:>12,.2f} {m['profit_pct']:>9.1%} "
                  f"{m['cagr']:>8.1%} {m['sharpe']:>+8.2f} {m['maxdd']:>+7.1%} {drag:>10,.2f}")

    # detailed quarterly + yearly for K=1 under gross / low-cost / realistic,
    # and K=2 realistic for leverage sensitivity.
    detailed = [
        ('gross_no_cost', cg, 1.0),
        ('low_cost_maker', cl, 1.0),
        ('realistic_taker', cr, 1.0),
        ('realistic_taker', cr, 2.0),
    ]
    for model_label, cost_series, K in detailed:
        r_net = K * (gross - cr)
        if model_label == 'gross_no_cost':
            r_net = K * (gross - cg)
        elif model_label == 'low_cost_maker':
            r_net = K * (gross - cl)
        elif model_label == 'realistic_taker':
            r_net = K * (gross - cr)
        m = _metric_returns(r_net, INIT_CAPITAL)
        print(f"\n{BAR}")
        print(f"  {model_label.upper()} — QUARTERLY PROFIT, K={K:.1f}, start $1,000")
        print(BAR)
        print(f"  {'Quarter':<12} {'Start $':>12} {'End $':>12} {'Profit $':>12} {'Return':>9}")
        for row in _period_table(m['equity'], 'Q'):
            print(f"  {row['period']:<12} {row['start']:>12,.2f} {row['end']:>12,.2f} "
                  f"{row['profit']:>12,.2f} {row['return_pct']:>8.1%}")
        print(f"\n  {model_label.upper()} — YEARLY PROFIT, K={K:.1f}")
        print(f"  {'Year':<12} {'Start $':>12} {'End $':>12} {'Profit $':>12} {'Return':>9}")
        for row in _period_table(m['equity'], 'Y'):
            print(f"  {row['period']:<12} {row['start']:>12,.2f} {row['end']:>12,.2f} "
                  f"{row['profit']:>12,.2f} {row['return_pct']:>8.1%}")

    out = {
        'assumptions': dict(init_capital=INIT_CAPITAL, fee_bps_round_trip=FEE_BPS_RT,
                            slippage_bps_round_trip=SLIP_BPS_RT,
                            funding_bps_per_day=FUNDING_BPS_PER_DAY,
                            combo='v58_full + equal-risk E7/B1/E6', k=k),
        'summary': summary,
    }
    out_path = Path(OUT_DIR) / 'v59_best_combo_1000_simulation.json'
    out_path.write_text(json.dumps(out, indent=2, default=float))
    print(f"\n  saved -> {out_path}")
    print(f"  total elapsed: {time.time()-t0:.1f}s")
    print(BAR)


if __name__ == '__main__':
    main()
