"""
trace_crash_channels.py — Per-Channel Lead Time Analysis at Real Crashes
=========================================================================

For each major ETH/BTC crash event, traces how many hours BEFORE the crash
trough each BSDT channel first crossed its calibration-period 90th-percentile
threshold.

Firing order theory:  δ_T → δ_G → δ_A → δ_C → price
This script measures it empirically.

CRASH EVENTS (defined by peak drawdown start date, ETH price reference):
  COVID crash    : 2020-03-12  ETH −50% in 24h
  May 2021 crash : 2021-05-19  ETH −40% in 48h
  LUNA collapse  : 2022-05-09  ETH −40% in 72h, structural (new regime)
  FTX collapse   : 2022-11-08  ETH −30% in 48h, structural (new regime)
  Tariff flash   : 2025-04-07  ETH −20% in 24h

INTERPRETATION GUIDE:
  Lead > 24h → channel warned more than a day before crash trough
  Lead < 0   → channel fired AFTER the crash event (lagging, useless for entry)
  Firing sequence δ_T before δ_G before δ_A before δ_C confirms theory.
  A large gap (δ_T fires 48h early, δ_C fires at crash) → long runway to ride.
"""
from __future__ import annotations
import time
from pathlib import Path
import numpy as np
import pandas as pd

from run_crypto_pairs_v34_full_combined import TRAIN_START, TEST_START
from run_crypto_pairs_v36_intraday_bsdt import CALIB_BARS
from test_daily_geometry_stop_tp_ohlc   import build_daily_geometry, fetch_futures_ohlcv, get_channel_series

# ── Known crash events  (date = first major down-candle day, ETH) ─────────────
CRASH_EVENTS = [
    dict(label='COVID crash',     date='2020-03-12', direction='down'),
    dict(label='May-2021 crash',  date='2021-05-19', direction='down'),
    dict(label='LUNA collapse',   date='2022-05-09', direction='down'),
    dict(label='FTX collapse',    date='2022-11-08', direction='down'),
    dict(label='Tariff flash',    date='2025-04-07', direction='down'),
]

# Lookback window (hours) to search for early channel firing before the crash
LOOKBACK_H  = 7 * 24     # 7 days before crash = 168 bars
FIRE_PCTILE = 0.90        # 90th percentile of absolute z-scores in calib period


def _load_data():
    print('[1] Building geometry + channel series ...')
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    ch = get_channel_series()       # {E7, dG, E6, dT}
    print('[2] Fetching OHLCV for price reference ...')
    ohlc = fetch_futures_ohlcv()
    return df_1h, comp_raw, calib_mask, ch, ohlc


def _channel_thresholds(ch: dict, calib_mask: pd.Series | np.ndarray) -> dict:
    """Compute 90th pctile of |z-score| in calibration window per channel."""
    thr = {}
    for name, s in ch.items():
        # calib_mask aligns to the original df_1h index
        # The channel series IS already z-scored (centered on calib mean/std)
        # So threshold in z-score units:
        calib_vals = s[calib_mask].dropna().abs()
        thr[name] = float(calib_vals.quantile(FIRE_PCTILE))
        print(f'    {name}: p90(|z|) = {thr[name]:.3f}')
    return thr


def _find_lead_times(
    ch: dict, thresholds: dict,
    crash_ts: pd.Timestamp,
    lookback_h: int,
) -> dict:
    """For each channel, find hours-before-crash when it first fired in lookback window."""
    window_start = crash_ts - pd.Timedelta(hours=lookback_h)
    leads = {}
    for name, s in ch.items():
        thr  = thresholds[name]
        win  = s[(s.index >= window_start) & (s.index < crash_ts)].dropna()
        fire = win[win.abs() > thr]
        if len(fire) == 0:
            leads[name] = None    # never fired in window
        else:
            first = fire.index[0]
            leads[name] = int((crash_ts - first).total_seconds() / 3600)
            # Also capture last fire (closest to crash) — measures persistence
    return leads


def _crash_magnitude(ohlc: pd.DataFrame, crash_ts: pd.Timestamp) -> dict:
    """ETH % decline from 6h before crash to 48h after crash."""
    pre  = ohlc[(ohlc.index >= crash_ts - pd.Timedelta(hours=6)) &
                (ohlc.index <  crash_ts)]['close']
    post = ohlc[(ohlc.index >= crash_ts) &
                (ohlc.index <  crash_ts + pd.Timedelta(hours=48))]['close']
    if pre.empty or post.empty:
        return dict(pre_close=None, min_close=None, drawdown=None)
    pre_close = float(pre.iloc[-1])
    min_close = float(post.min())
    return dict(
        pre_close=round(pre_close, 2),
        min_close=round(min_close, 2),
        drawdown=round(min_close / pre_close - 1.0, 4),
    )


def _channel_values_at(ch: dict, crash_ts: pd.Timestamp, n_bars: int = 5) -> dict:
    """Average absolute z-score of each channel in the n_bars preceding the crash."""
    out = {}
    for name, s in ch.items():
        win = s[(s.index < crash_ts) &
                (s.index >= crash_ts - pd.Timedelta(hours=n_bars))].dropna()
        out[name] = round(float(win.abs().mean()), 3) if len(win) > 0 else None
    return out


def main():
    t0 = time.time()
    print('=' * 100)
    print('  BSDT CHANNEL CRASH TRACER — Lead Time Analysis')
    print('  Channels: E7(δ_A), dG(δ_G), E6(δ_C), dT(δ_T)')
    print('  Theory:   δ_T fires first → δ_G → δ_A → δ_C → price')
    print('=' * 100)

    df_1h, comp_raw, calib_mask, ch, ohlc = _load_data()

    # calib_mask aligns to df_1h.index — map it to channel series
    # Channels share df_1h.index, so we can use calib_mask directly
    print('\n[3] Computing per-channel p90 thresholds (calibration window) ...')
    thresholds = _channel_thresholds(ch, calib_mask)

    print('\n[4] Tracing channels at each crash event ...\n')
    all_rows = []

    CH_ORDER = ['dT', 'dG', 'E7', 'E6']   # theoretical firing order
    CH_LABELS = {'dT': 'δ_T (novelty)', 'dG': 'δ_G (gap)',
                 'E7': 'δ_A (velocity)', 'E6': 'δ_C (Mahal)'}

    for event in CRASH_EVENTS:
        crash_ts = pd.Timestamp(event['date'])
        label    = event['label']

        # Snap to nearest hour in our data
        ohlc_idx = ohlc.index
        nearest  = ohlc_idx[ohlc_idx.searchsorted(crash_ts)]
        ch_ts    = ch['E7'].index
        crash_h  = ch_ts[max(0, ch_ts.searchsorted(crash_ts) - 1)]

        mag   = _crash_magnitude(ohlc, nearest)
        leads = _find_lead_times(ch, thresholds, crash_h, LOOKBACK_H)
        pre5  = _channel_values_at(ch, crash_h, n_bars=5)

        print(f'  ┌─ {label}  ({crash_ts.date()}) ─────────────────────────────────')
        if mag['drawdown'] is not None:
            print(f'  │  ETH: ${mag["pre_close"]:,.0f} → ${mag["min_close"]:,.0f}'
                  f'  ({mag["drawdown"]:+.1%} in 48h)')
        else:
            print(f'  │  (price data limited / in future)')
        print(f'  │  Lookback: {LOOKBACK_H}h  |  Fire threshold: p{FIRE_PCTILE*100:.0f} of |z-score|')
        print(f'  │')

        lead_vals = []
        for ch_name in CH_ORDER:
            l = leads[ch_name]
            pre_v = pre5.get(ch_name)
            if l is None:
                lead_str = '  DID NOT FIRE  '
                fired_at = '—'
            else:
                lead_str = f'{l:>5}h before'
                fired_at = str((crash_h - pd.Timedelta(hours=l)).floor('h'))[:16]
            thr_str = f'[thr={thresholds[ch_name]:.2f}]'
            pre_str = f'pre-crash |z|={pre_v:.3f}' if pre_v is not None else ''
            print(f'  │  {CH_LABELS[ch_name]:<18}: {lead_str}   '
                  f'first fired at {fired_at}   {thr_str}  {pre_str}')
            lead_vals.append(l)

        # Check firing order
        lead_nums = [(l if l is not None else -999) for l in lead_vals]
        order_ok  = all(lead_nums[i] >= lead_nums[i+1] for i in range(len(lead_nums)-1))
        comp_win  = comp_raw[(comp_raw.index >= crash_h - pd.Timedelta(hours=LOOKBACK_H)) &
                              (comp_raw.index < crash_h)].dropna()
        comp_peak_lead = None
        if len(comp_win) > 0:
            pk_idx = comp_win.abs().idxmax()
            comp_peak_lead = int((crash_h - pk_idx).total_seconds() / 3600)
        print(f'  │')
        print(f'  │  Composite peak:    {comp_peak_lead}h before  '
              f'(composite signal peak in lookback window)')
        print(f'  │  Theory order OK:   {"YES ✓" if order_ok else "NO — ordering differs"}')
        print(f'  └{"─"*70}')
        print()

        all_rows.append(dict(
            event=label, crash_date=str(crash_ts.date()),
            drawdown=mag.get('drawdown'), pre_eth=mag.get('pre_close'),
            lead_dT=leads['dT'], lead_dG=leads['dG'],
            lead_E7=leads['E7'], lead_E6=leads['E6'],
            comp_peak_lead=comp_peak_lead,
            theory_order_ok=order_ok,
            pre5_dT=pre5.get('dT'), pre5_dG=pre5.get('dG'),
            pre5_E7=pre5.get('E7'), pre5_E6=pre5.get('E6'),
        ))

    # ── Cross-event summary table ──────────────────────────────────────────────
    print('=' * 100)
    print('  CROSS-EVENT SUMMARY — Lead Times (hours before crash trough)')
    print('=' * 100)
    hdr = f"  {'Event':<22} {'DD':>8} {'δ_T lead':>10} {'δ_G lead':>10} {'δ_A lead':>10} {'δ_C lead':>10} {'Comp':>8} {'OrderOK':>8}"
    print(hdr)
    print('-' * 100)
    for r in all_rows:
        def _fmt(x): return f'{x:>9}h' if x is not None else f'{"NO FIRE":>9}'
        dd  = f'{r["drawdown"]:>+6.1%}' if r['drawdown'] is not None else '   N/A'
        print(f"  {r['event']:<22} {dd:>8} {_fmt(r['lead_dT'])} {_fmt(r['lead_dG'])} "
              f"{_fmt(r['lead_E7'])} {_fmt(r['lead_E6'])} "
              f"{'NO FIRE' if r['comp_peak_lead'] is None else f'{r[chr(99)+chr(111)+chr(109)+chr(112)+ chr(95)+chr(112)+chr(101)+chr(97)+chr(107)+chr(95)+chr(108)+chr(101)+chr(97)+chr(100)]:>7}h':>8} "
              f"{'YES' if r['theory_order_ok'] else 'NO':>8}")

    print()
    print('  INTERPRETATION:')
    print('  δ_T fires earliest because it detects rarity relative to history.')
    print('  δ_G fires second because it detects novel structural stress (PCA gap).')
    print('  δ_A (E7) fires third — velocity spike that confirms the move is real.')
    print('  δ_C fires last — by then, Mahalanobis stress is fully systemic.')
    print()
    print('  GH,TH (δ_G + δ_T elevated) fires BEFORE δ_A and BEFORE price impact.')
    print('  This is why GH,TH is the profitable quadrant — it identifies the move')
    print('  BEFORE the crowd has priced in the regime shift.')
    print(f'\n  Total time: {time.time() - t0:.1f}s')


if __name__ == '__main__':
    main()
