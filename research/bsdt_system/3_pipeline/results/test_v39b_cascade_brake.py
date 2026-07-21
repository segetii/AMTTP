"""v39b ψ / BSDT adaptive-friction cascade brake test.

Purpose
-------
The user expectation is correct: BSDT/adaptive friction should warn before the
equity curve enters a cascade, not only react after drawdown. This test uses
pre-trade BSDT quantities as a *forward risk throttle*:

  - cos_psi_4ch: four-channel geometric alignment / consistency
  - a_G: structural stress attribution
  - R_t_4ch: controllability / gradient amplification proxy

Then combines the best pre-drawdown brake with the already-tested adaptive Y
(equity drawdown brake). No live/paper orders.
"""
from __future__ import annotations
import sys
import json, time
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')

from collapse_geometry import MasterOperator
from run_crypto_pairs_v34_full_combined import OUT_DIR, TRAIN_START, TEST_START
from run_crypto_pairs_v36_intraday_bsdt import CALIB_BARS, build_intraday_state_panel
from run_crypto_pairs_v39_four_channels import calibrate_firing_thresholds, FIRE_PERCENTILE
from run_crypto_pairs_v39b_k1_scaled import compute_four_channel_signals_v39b, calibrate_channel_means, PCA_K_B
from run_robustness_validation import _cached_fetch_binance_funding
from test_daily_geometry_stop_tp_ohlc import build_daily_geometry, fetch_futures_ohlcv
from test_psi_adaptive_y import simulate_unit_with_psi, equity_no_y, BASE, Y_CFG
from simulate_adaptive_y_drawdown_brake import adaptive_equity
from simulate_hourly_2h_daily_risk_ohlc_fast import period

OUT = Path(OUT_DIR) / 'v39b_cascade_brake_results.json'


def compute_v39b(df_1h, calib_mask):
    fund = _cached_fetch_binance_funding()
    X = np.nan_to_num(build_intraday_state_panel(df_1h, fund.get('BTCUSDT'), fund.get('ETHUSDT')))
    if len(X) != len(df_1h):
        n = min(len(X), len(df_1h)); X = X[:n]; df_1h = df_1h.iloc[:n]; calib_mask = calib_mask[:n]
    print('  [v39b] calibrating k=1 operator...', flush=True)
    M_k1 = MasterOperator.calibrate(X[calib_mask], k=PCA_K_B)
    print('  [v39b] channel means...', flush=True)
    mu = calibrate_channel_means(X, calib_mask, M_k1)
    print('  [v39b] firing thresholds...', flush=True)
    fire = calibrate_firing_thresholds(X, calib_mask, M_k1, pct=FIRE_PERCENTILE)
    print('  [v39b] four-channel sweep...', flush=True)
    sig = compute_four_channel_signals_v39b(X, df_1h, M_k1, pd.DataFrame(index=df_1h.index), fire, mu)
    return sig.reindex(df_1h.index).ffill()


def prep_base_arrays():
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    ohlc = fetch_futures_ohlcv()
    common_start = comp_raw.dropna().index.min(); common_end = comp_raw.dropna().index.max()
    ohlc = ohlc[(ohlc.index >= common_start) & (ohlc.index <= common_end) & (ohlc.index >= pd.Timestamp(TEST_START))].copy()
    hours = ohlc.index
    op = ohlc['open'].values.astype(float); hi = ohlc['high'].values.astype(float); lo = ohlc['low'].values.astype(float); cl = ohlc['close'].values.astype(float)
    hourly_cal = comp_raw[calib_mask].abs().dropna(); hth = float(hourly_cal.quantile(BASE['q_hourly']))
    sig_shifted = comp_raw.shift(1).reindex(hours).fillna(0.0).values.astype(float)
    hpos = np.where(np.abs(sig_shifted) >= hth, np.sign(sig_shifted).astype(int), 0)

    daily_sig = comp_raw.groupby(comp_raw.index.normalize()).last()
    all_ohlc = fetch_futures_ohlcv(); all_days = pd.Index(sorted(all_ohlc.index.normalize().unique()))
    calib_days = all_days[(all_days >= pd.Timestamp(TRAIN_START)) & (all_days < pd.Timestamp(TEST_START))]
    ret_daily = all_ohlc['close'].pct_change().fillna(0.0).groupby(all_ohlc.index.normalize()).sum()
    daily_vol = float(ret_daily.reindex(calib_days).std())
    dth = float(daily_sig.reindex(calib_days).abs().dropna().quantile(BASE['q_daily']))
    prev_days = hours.normalize() - pd.Timedelta(days=1)
    ds_vals = daily_sig.reindex(prev_days).fillna(0.0).values.astype(float)
    dpos = np.sign(ds_vals).astype(int); dactive = np.abs(ds_vals) >= dth
    return df_1h, calib_mask, hours, op, hi, lo, cl, hpos, dpos, dactive, daily_vol


def main():
    t0 = time.time()
    print('='*100)
    print('  v39b ψ / BSDT CASCADE BRAKE TEST')
    print('='*100)
    df_1h, calib_mask, hours, op, hi, lo, cl, hpos, dpos, dactive, daily_vol = prep_base_arrays()
    sig4 = compute_v39b(df_1h, calib_mask)
    s4 = sig4.shift(1).reindex(hours).ffill().fillna(0.0)
    cospsi = s4['cos_psi_4ch'].clip(-1, 1).values.astype(float)
    aG = s4['a_G'].clip(0, 1).values.astype(float)
    R = s4['R_t_4ch'].replace([np.inf, -np.inf], np.nan).ffill().fillna(1.0).values.astype(float)

    # Calibration thresholds from pre-test/calibration period.
    cal = sig4.loc[(sig4.index >= TRAIN_START) & (sig4.index < TEST_START)]
    cos_floor = float(cal['cos_psi_4ch'].quantile(0.20))
    aG_hi = float(cal['a_G'].quantile(0.80))
    R_hi = float(cal['R_t_4ch'].replace([np.inf, -np.inf], np.nan).quantile(0.80))
    print(f'  thresholds: cos20={cos_floor:.3f}, aG80={aG_hi:.3f}, R80={R_hi:.3f}')

    # Pre-drawdown cascade multipliers. These are causal because all signals are shifted 1h.
    variants = {
        'no_cascade': np.ones(len(hours)),
        'psi_soft': np.clip(cospsi, 0.0, 1.0),
        'psi_hard_cal20': (cospsi >= cos_floor).astype(float),
        'structural_aG_soft': np.where(aG > aG_hi, 0.50, 1.0),
        'R_high_soft': np.where(R > R_hi, 0.50, 1.0),
        'cascade_combo': np.clip(cospsi, 0.0, 1.0) * np.where(aG > aG_hi, 0.50, 1.0) * np.where(R > R_hi, 0.70, 1.0),
        'cascade_binary': ((cospsi >= cos_floor) & (aG <= aG_hi) & (R <= R_hi)).astype(float),
    }

    rows = []
    for name, mult in variants.items():
        unit_arr, counts = simulate_unit_with_psi(op, hi, lo, cl, hpos, dpos, dactive, mult, BASE['sl_mult']*daily_vol, BASE['tp_mult']*daily_vol)
        unit = pd.Series(unit_arr, index=hours)
        raw = equity_no_y(unit, Y_CFG['leverage'])
        y = adaptive_equity(unit, Y_CFG['leverage'], Y_CFG['dd_soft'], Y_CFG['dd_stop'], Y_CFG['y_floor'])
        rows.append(dict(variant=name, avg_cascade_y=float(np.mean(mult)), pct_block=float(np.mean(mult <= 1e-12)),
                         raw_final=raw['final'], raw_sharpe=raw['sharpe'], raw_maxdd=raw['maxdd'],
                         y_final=y['final'], y_profit=y['profit'], y_sharpe=y['sharpe'], y_maxdd=y['maxdd'],
                         y_avg=y['avg_y'], y_pct_cut=y['pct_cut'], **counts))
    rows = sorted(rows, key=lambda r: (r['y_final'], r['y_sharpe']), reverse=True)
    selected = rows[0]
    unit_arr, counts = simulate_unit_with_psi(op, hi, lo, cl, hpos, dpos, dactive, variants[selected['variant']], BASE['sl_mult']*daily_vol, BASE['tp_mult']*daily_vol)
    y = adaptive_equity(pd.Series(unit_arr, index=hours), Y_CFG['leverage'], Y_CFG['dd_soft'], Y_CFG['dd_stop'], Y_CFG['y_floor'])
    yearly = period(y['eq'], 'Y')

    print(f"\n  {'Variant':<18} {'AvgPreY':>7} {'Block%':>7} {'Entries':>7} {'Raw$':>10} {'RawDD':>8} {'Y$':>10} {'YSh':>7} {'YDD':>8} {'EqY':>5}")
    for r in rows:
        print(f"  {r['variant']:<18} {r['avg_cascade_y']:>7.2f} {r['pct_block']:>6.1%} {r['entries']:>7} {r['raw_final']:>10,.0f} {r['raw_maxdd']:>+7.1%} {r['y_final']:>10,.0f} {r['y_sharpe']:>+7.2f} {r['y_maxdd']:>+7.1%} {r['y_avg']:>5.2f}")
    print(f"\n  SELECTED: {selected['variant']} + adaptive Y")
    print(f"  final=${y['final']:,.2f} profit=${y['profit']:,.2f} sharpe={y['sharpe']:+.2f} maxDD={y['maxdd']:.1%}")
    OUT.write_text(json.dumps({'base_config': BASE, 'adaptive_y': Y_CFG,
                               'thresholds': {'cos20': cos_floor, 'aG80': aG_hi, 'R80': R_hi},
                               'rows': rows, 'selected': selected, 'selected_yearly': yearly,
                               'elapsed_seconds': time.time()-t0}, indent=2, default=float))
    print(f"  saved -> {OUT}\n  elapsed={time.time()-t0:.1f}s")

if __name__ == '__main__':
    main()
