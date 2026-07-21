"""Enterprise offline trade-plan generator (no paper/live orders).

Combines the resolved research layers into an expert-style daily plan:
  - v59 geometry composite = (z(E7)+z(B1)+z(E6))/3
    - corrected hourly execution with daily-size mode
    - closed-form dynamic sizing = K × strength × quality × vol-target × gamma × adaptive-Y
    - true-OHLC validated stop/take-profit defaults from the corrected hourly sweep
  - maker-only execution assumption

This script DOES NOT place orders. It produces a JSON plan that can later feed a
paper/live executor after the remaining exchange-integration work is approved.
"""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
import pandas as pd

from run_crypto_pairs_v34_full_combined import OUT_DIR, TRAIN_START, TEST_START
from run_crypto_pairs_v36_intraday_bsdt import CALIB_BARS
from test_daily_geometry_stop_tp_ohlc import build_daily_geometry, fetch_futures_ohlcv
from test_dynamic_profit_sizing import Y_CFG as DYN_Y_CFG, prepare as prepare_dynamic
from test_psi_adaptive_y import BASE as DYN_BASE, simulate_unit_with_psi
from simulate_adaptive_y_drawdown_brake import adaptive_equity

OUT = Path(OUT_DIR) / 'enterprise_trade_plan_latest.json'
Q_2H = 0.80
Q_DAILY = 0.90
# Conservative true-OHLC setting from q=.90 safety table: last signal, SL=0.5σ, TP=0.75σ.
DAILY_SIGNAL = 'last'
SL_SIGMA = 0.50
TP_SIGMA = 0.75
# ATR-based stop/TP — standard technical analysis method (Wilder ATR14).
# SL  = entry ± ATR_SL_MULT × ATR14     (standard 2× ATR stop)
# TP  = entry ± ATR_TP_MULT × ATR14     (3× ATR → 1.5 : 1 reward/risk)
ATR_PERIOD   = 14
ATR_SL_MULT  = 2.0
ATR_TP_MULT  = 3.0
MAX_LEVERAGE_EXPERT = 2.0
MAX_LEVERAGE_RESEARCH_CAP = 5.0
# In daily-signal mode the geometry bar timestamp naturally lags the market by
# up to one trading day.  A 3 h window was far too strict; 36 h accommodates
# any realistic geometry-to-market offset while still rejecting genuinely stale
# signals (e.g.  missed several overnight sessions).
MAX_SIGNAL_MARKET_LAG_HOURS = 36.0

# Current best dynamic-profit sizing setting from test_dynamic_profit_sizing.py.
DYN_K = 3.0
DYN_STRENGTH_CAP = 2.5
DYN_VOL_CAP = 3.0
DYN_GAMMA_MODE = 'convex'
DYN_TOTAL_CAP = 2.0


def zscore(s, mask):
    return (s - s[mask].mean()) / max(s[mask].std(), 1e-12)


def percentile_against(value, calibration_values):
    cal = np.asarray(pd.Series(calibration_values).dropna().values, dtype=float)
    if len(cal) == 0 or not np.isfinite(value):
        return 0.0
    return float(np.searchsorted(np.sort(cal), float(value), side='right') / len(cal))


def y_from_drawdown(dd, dd_soft, dd_stop, y_floor):
    if dd <= dd_soft:
        return 1.0
    if dd >= dd_stop:
        return y_floor
    return y_floor + (1.0 - y_floor) * (dd_stop - dd) / (dd_stop - dd_soft)


def selected_dynamic_stream(p):
    strength_mult = np.clip(0.25 + DYN_STRENGTH_CAP * p['strength_raw'], 0.25, DYN_STRENGTH_CAP)
    vol_mult = np.clip(p['vol_base'], 0.25, DYN_VOL_CAP)
    if DYN_GAMMA_MODE == 'linear':
        gamma = np.clip(1.5 - p['stress_rank'], 0.5, 1.2)
    else:
        delta = 1.2 - p['stress_rank']
        gamma = np.clip(np.sign(delta) * delta * delta, 0.4, 1.3)
    size_mult = np.clip(strength_mult * p['q_quality'] * vol_mult * gamma, 0.0, DYN_TOTAL_CAP)
    unit_arr, counts = simulate_unit_with_psi(
        p['op'], p['hi'], p['lo'], p['cl'], p['hpos'], p['dpos'], p['dactive'], size_mult,
        DYN_BASE['sl_mult'] * p['daily_vol'], DYN_BASE['tp_mult'] * p['daily_vol'],
    )
    unit = pd.Series(unit_arr, index=p['hours'])
    y_hist = adaptive_equity(unit, DYN_K, DYN_Y_CFG['dd_soft'], DYN_Y_CFG['dd_stop'], DYN_Y_CFG['y_floor'])
    current_eq = float(y_hist['eq'].iloc[-1])
    current_peak = float(y_hist['eq'].cummax().iloc[-1])
    current_dd = max(0.0, 1.0 - current_eq / max(current_peak, 1e-12))
    current_y = y_from_drawdown(current_dd, DYN_Y_CFG['dd_soft'], DYN_Y_CFG['dd_stop'], DYN_Y_CFG['y_floor'])

    roll_mu = float(unit.rolling(240, min_periods=72).mean().shift(1).iloc[-1])
    roll_sd = float(unit.rolling(240, min_periods=72).std().shift(1).iloc[-1])
    if not np.isfinite(roll_mu):
        roll_mu = 0.0
    if not np.isfinite(roll_sd) or roll_sd <= 0:
        roll_sd = float(unit.std()) if float(unit.std()) > 0 else 1e-8
    return dict(
        strength_mult=strength_mult,
        vol_mult=vol_mult,
        gamma=gamma,
        size_mult=size_mult,
        unit=unit,
        counts=counts,
        y_hist=y_hist,
        current_equity=current_eq,
        current_peak=current_peak,
        current_drawdown=current_dd,
        current_y=current_y,
        rolling_unit_mu=roll_mu,
        rolling_unit_sigma=roll_sd,
    )


def main():
    t0 = time.time()
    df_1h, comp_hourly, calib_mask = build_daily_geometry()
    dyn = prepare_dynamic()
    dyn_stream = selected_dynamic_stream(dyn)
    ohlc = fetch_futures_ohlcv()
    market_latest_time = ohlc.dropna().index[-1]
    market_latest_price = float(ohlc['close'].dropna().iloc[-1])

    # --- ATR14 (standard stop-loss method) ---
    _tr = pd.concat([
        ohlc['high'] - ohlc['low'],
        (ohlc['high'] - ohlc['close'].shift(1)).abs(),
        (ohlc['low']  - ohlc['close'].shift(1)).abs(),
    ], axis=1).max(axis=1)
    _atr14 = _tr.ewm(span=ATR_PERIOD, adjust=False).mean()
    latest_atr  = float(_atr14.dropna().iloc[-1])
    atr_sl_dist = ATR_SL_MULT * latest_atr
    atr_tp_dist = ATR_TP_MULT * latest_atr
    idx = df_1h.index
    train_1h = (idx >= TRAIN_START) & (idx < TEST_START)
    train_idx = np.where(train_1h)[0]
    calib2_mask = np.zeros(len(df_1h), dtype=bool)
    calib2_mask[train_idx[-CALIB_BARS:]] = True

    abs_cal_hourly = comp_hourly[calib2_mask].abs().dropna()
    th_2h = float(abs_cal_hourly.quantile(Q_2H))
    th_hourly_dynamic = float(abs_cal_hourly.quantile(DYN_BASE['q_hourly']))
    signal_candidates = comp_hourly.dropna().loc[:market_latest_time]
    if signal_candidates.empty:
        raise RuntimeError('No geometry signal is available at or before latest market OHLC')
    latest_hour = signal_candidates.index[-1]  # geometry timestamp for lag check

    # Use the same lagged signal the backtest uses: comp.shift(1) gives the
    # signal from the PREVIOUS df_1h bar at every bar, eliminating intra-bar
    # look-ahead.  At the latest geometry bar this is the value that drove
    # the position in the simulation.
    comp_lagged = comp_hourly.shift(1)
    _lagged_val = comp_lagged.reindex([latest_hour]).iloc[0]
    if pd.notna(_lagged_val):
        latest_2h_signal = float(_lagged_val)
    else:
        # Edge-case: first ever bar in the series has no prior; fall back to unshifted.
        latest_2h_signal = float(comp_hourly.loc[latest_hour])

    hourly_active = abs(latest_2h_signal) >= th_2h
    hourly_dynamic_active = abs(latest_2h_signal) >= th_hourly_dynamic
    hourly_bias = 'LONG' if latest_2h_signal > 0 else 'SHORT'
    hourly_q = percentile_against(abs(latest_2h_signal), abs_cal_hourly)

    daily_signals = {
        'last': comp_hourly.groupby(comp_hourly.index.normalize()).last(),
        'mean': comp_hourly.groupby(comp_hourly.index.normalize()).mean(),
        'absmax': comp_hourly.groupby(comp_hourly.index.normalize()).apply(lambda s: s.loc[s.abs().idxmax()] if len(s.dropna()) else np.nan),
    }
    ret_daily = ohlc['close'].pct_change().fillna(0.0).groupby(ohlc.index.normalize()).sum()
    days = pd.Index(sorted(ret_daily.index.unique()))
    calib_days = days[(days >= pd.Timestamp(TRAIN_START)) & (days < pd.Timestamp(TEST_START))]
    daily_vol = float(ret_daily.reindex(calib_days).std())

    sig = daily_signals[DAILY_SIGNAL]
    th_daily = float(sig.reindex(calib_days).abs().dropna().quantile(Q_DAILY))
    th_daily_dynamic = float(sig.reindex(calib_days).abs().dropna().quantile(DYN_BASE['q_daily']))
    # Match the simulation lifecycle: an hourly trade uses the previous completed
    # day as context, not an incomplete same-day daily aggregate.
    latest_day = latest_hour.normalize() - pd.Timedelta(days=1)
    if latest_day not in sig.dropna().index:
        latest_day = sig.dropna().loc[:latest_day].index[-1]
    latest_daily_signal = float(sig.loc[latest_day])
    daily_active = abs(latest_daily_signal) >= th_daily
    daily_dynamic_active = abs(latest_daily_signal) >= th_daily_dynamic
    daily_bias = 'LONG' if latest_daily_signal > 0 else 'SHORT'
    daily_q = percentile_against(abs(latest_daily_signal), sig.reindex(calib_days).abs().dropna())

    signal_market_lag_hours = float((market_latest_time - latest_hour) / pd.Timedelta(hours=1))
    data_fresh = signal_market_lag_hours <= MAX_SIGNAL_MARKET_LAG_HOURS
    # Entry price uses the current live market price (not the geometry-snapshot price)
    # so that stop/TP levels are anchored to where the market is now.
    latest_price = market_latest_price
    sl_ret = DYN_BASE['sl_mult'] * daily_vol
    tp_ret = DYN_BASE['tp_mult'] * daily_vol

    dyn_hour_indexer = dyn['hours'].get_indexer([latest_hour], method='pad')
    latest_dyn_i = int(dyn_hour_indexer[0]) if len(dyn_hour_indexer) and dyn_hour_indexer[0] >= 0 else -1
    daily_confirm = bool(daily_dynamic_active and daily_bias == hourly_bias)
    dynamic_strength_score = float(hourly_q * (1.0 + daily_q) * (1.0 + float(daily_confirm)))
    dynamic_strength_norm = dynamic_strength_score / 4.0
    dynamic_size_multiplier = float(dyn_stream['size_mult'][latest_dyn_i])
    dynamic_strength_multiplier = float(dyn_stream['strength_mult'][latest_dyn_i])
    dynamic_quality_multiplier = float(dyn['q_quality'][latest_dyn_i])
    dynamic_vol_multiplier = float(dyn_stream['vol_mult'][latest_dyn_i])
    dynamic_gamma_multiplier = float(dyn_stream['gamma'][latest_dyn_i])
    dynamic_y = float(dyn_stream['current_y'])
    effective_leverage = float(DYN_K * dynamic_size_multiplier * dynamic_y)
    expected_log_growth = float(
        effective_leverage * dyn_stream['rolling_unit_mu']
        - 0.5 * (effective_leverage ** 2) * (dyn_stream['rolling_unit_sigma'] ** 2)
    )
    log_growth_ok = bool(expected_log_growth > 0.0)

    aligned = daily_active and hourly_active and (daily_bias == hourly_bias)
    # log_growth_ok is a risk indicator but NOT a hard gate: adaptive Y already
    # reduces exposure during drawdowns, so blocking trades entirely here would
    # diverge from the backtest behaviour (which had no log-growth veto).
    dynamic_trade_ok = data_fresh and hourly_dynamic_active and (not daily_dynamic_active or daily_bias == hourly_bias) and effective_leverage > 0
    if not dynamic_trade_ok:
        decision = 'FLAT'
        leverage = 0.0
        stop_price = None
        take_profit_price = None
        if not data_fresh:
            reason = f'Data stale: geometry latest hour is {signal_market_lag_hours:.1f}h behind latest market OHLC (max {MAX_SIGNAL_MARKET_LAG_HOURS:.0f}h allowed).'
        elif not hourly_dynamic_active:
            reason = 'Dynamic hourly gate is inactive (|signal| below 50th-pct calibration threshold).'
        elif daily_dynamic_active and daily_bias != hourly_bias:
            reason = 'Dynamic daily context conflicts with hourly direction.'
        else:
            reason = 'Dynamic sizing returned no usable exposure.'
    else:
        decision = hourly_bias
        leverage = effective_leverage
        if leverage > MAX_LEVERAGE_EXPERT:
            print(f'  [WARN] effective_leverage {leverage:.2f}x exceeds expert cap '
                  f'{MAX_LEVERAGE_EXPERT}x; executor should cap at {MAX_LEVERAGE_EXPERT}x')
        if decision == 'LONG':
            stop_price        = latest_price - atr_sl_dist
            take_profit_price = latest_price + atr_tp_dist
        else:
            stop_price        = latest_price + atr_sl_dist
            take_profit_price = latest_price - atr_tp_dist
        lg_note = '' if log_growth_ok else ' (log-growth negative — adaptive-Y already scaling exposure down)'
        reason = f'Hourly dynamic gate is active; daily context does not conflict.{lg_note}'

    plan = {
        'generated_at_utc': pd.Timestamp.utcnow().isoformat(),
        # Geometry data coverage
        'geometry_latest_hour': str(latest_hour),
        'geometry_lag_hours': signal_market_lag_hours,
        'geometry_lag_max_hours': MAX_SIGNAL_MARKET_LAG_HOURS,
        'data_fresh': bool(data_fresh),
        # Market data
        'market_latest_time': str(market_latest_time),
        'market_latest_price_eth': market_latest_price,
        # Signal (lagged, as used in backtest)
        'hourly_signal_used': latest_2h_signal,
        'hourly_signal_unshifted': float(comp_hourly.loc[latest_hour]),
        # Decision
        'decision': decision,
        'reason': reason,
        'recommended_effective_leverage': leverage,
        'leverage_expert_cap': MAX_LEVERAGE_EXPERT,
        'maker_only_required': True,
        'dynamic_closed_form_layer': {
            'enabled': True,
            'formula': 'L = K × strength × rolling_quality × vol_target × gamma_dial × adaptive_Y',
            'base_K': DYN_K,
            'strength_cap': DYN_STRENGTH_CAP,
            'vol_cap': DYN_VOL_CAP,
            'gamma_mode': DYN_GAMMA_MODE,
            'size_multiplier_cap': DYN_TOTAL_CAP,
            'adaptive_y': DYN_Y_CFG,
            'hourly_q': hourly_q,
            'daily_q': daily_q,
            'daily_confirm': daily_confirm,
            'strength_score': dynamic_strength_score,
            'strength_norm': dynamic_strength_norm,
            'strength_multiplier': dynamic_strength_multiplier,
            'rolling_quality_multiplier': dynamic_quality_multiplier,
            'volatility_multiplier': dynamic_vol_multiplier,
            'gamma_multiplier': dynamic_gamma_multiplier,
            'pre_y_size_multiplier': dynamic_size_multiplier,
            'current_equity_proxy': dyn_stream['current_equity'],
            'current_peak_proxy': dyn_stream['current_peak'],
            'current_drawdown_proxy': dyn_stream['current_drawdown'],
            'adaptive_y_current': dynamic_y,
            'effective_leverage': effective_leverage,
            'rolling_unit_mu': dyn_stream['rolling_unit_mu'],
            'rolling_unit_sigma': dyn_stream['rolling_unit_sigma'],
            'expected_log_growth_approx': expected_log_growth,
            'log_growth_gate_ok': log_growth_ok,
            'historical_dynamic_counts': dyn_stream['counts'],
        },
        'daily_layer': {
            'signal_type': DAILY_SIGNAL,
            'legacy_q': Q_DAILY,
            'dynamic_q': DYN_BASE['q_daily'],
            'threshold': th_daily,
            'dynamic_threshold': th_daily_dynamic,
            'latest_day': str(latest_day.date()),
            'signal': latest_daily_signal,
            'abs_signal': abs(latest_daily_signal),
            'active': bool(daily_active),
            'dynamic_active': bool(daily_dynamic_active),
            'bias': daily_bias,
            'daily_vol_sigma': daily_vol,
            'stop_loss_sigma': DYN_BASE['sl_mult'],
            'take_profit_sigma': DYN_BASE['tp_mult'],
            'stop_loss_return': sl_ret,
            'take_profit_return': tp_ret,
        },
        'hourly_2h_layer': {
            'legacy_q': Q_2H,
            'dynamic_q': DYN_BASE['q_hourly'],
            'threshold': th_2h,
            'dynamic_threshold': th_hourly_dynamic,
            'latest_hour': str(latest_hour),
            'signal': latest_2h_signal,
            'abs_signal': abs(latest_2h_signal),
            'active': bool(hourly_active),
            'dynamic_active': bool(hourly_dynamic_active),
            'bias': hourly_bias,
        },
        'risk_prices': {
            'method': 'ATR14',
            'entry_price': float(market_latest_price),
            'atr14_value': float(latest_atr),
            'sl_atr_mult': ATR_SL_MULT,
            'tp_atr_mult': ATR_TP_MULT,
            'reward_risk_ratio': ATR_TP_MULT / ATR_SL_MULT,
            'sl_distance_usd': float(atr_sl_dist),
            'tp_distance_usd': float(atr_tp_dist),
            'sl_pct': float(atr_sl_dist / market_latest_price * 100),
            'tp_pct': float(atr_tp_dist / market_latest_price * 100),
            'stop_price': None if stop_price is None else float(stop_price),
            'take_profit_price': None if take_profit_price is None else float(take_profit_price),
        },
        'hard_risk_rules': [
            'No taker entries except emergency exit.',
            'No trade if active daily context conflicts with hourly direction.',
            'No trade if hourly dynamic confidence gate is inactive (|signal| < 50th-pct threshold).',
            'No trade if geometry signal lag exceeds MAX_SIGNAL_MARKET_LAG_HOURS.',
            'Adaptive-Y automatically scales exposure down during drawdowns.',
            'Use reduce-only stop/TP orders after entry.',
            'K=5 leverage remains research-only until exchange execution validation is complete.',
        ],
        'legacy_enterprise_gate_for_comparison': {
            'aligned': bool(aligned),
            'daily_q': Q_DAILY,
            'hourly_q': Q_2H,
            'would_trade': bool(aligned),
        },
        'elapsed_seconds': time.time() - t0,
    }
    OUT.write_text(json.dumps(plan, indent=2, default=float))
    print(json.dumps(plan, indent=2, default=float))
    print(f"\nSaved -> {OUT}")


if __name__ == '__main__':
    main()
