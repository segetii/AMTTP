"""Integrated enterprise simulation: daily risk gate + 2h/hourly entry + true OHLC stops.

No live/paper trading. This is a historical execution simulation.

Rules
-----
- Daily risk gate: previous daily geometry `last`, q=0.90.
- Hourly/2h entry gate: geometry composite, q=0.80.
- Direction must agree between daily and hourly layers.
- One trade max per day.
- Enter at the next hourly candle open after an aligned hourly signal.
- Exit at true OHLC stop/TP or day-end close.
- Conservative same-candle ambiguity: stop before TP.
- Maker low-cost model: 2 bps round-trip + 0.5 bps/day funding.
- Report expert K=2 and research K=5.
"""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
import pandas as pd

from run_crypto_pairs_v34_full_combined import OUT_DIR, TRAIN_START, TEST_START
from run_crypto_pairs_v36_intraday_bsdt import CALIB_BARS
from test_daily_geometry_stop_tp_ohlc import build_daily_geometry, fetch_futures_ohlcv

INIT = 1000.0
Q_DAILY = 0.90
Q_HOURLY = 0.80
SL_SIGMA = 0.50
TP_SIGMA = 0.75
RT_COST = 2.0 / 1e4
FUND_DAY = 0.5 / 1e4
OUT = Path(OUT_DIR) / 'enterprise_daily_2h_ohlc_simulation.json'


def _equity(r, init=INIT, periods_per_year=365.25):
    r = pd.Series(r).fillna(0.0).clip(lower=-0.95)
    eq = init * (1.0 + r).cumprod()
    dd = (eq - eq.cummax()) / eq.cummax()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    return dict(final=float(eq.iloc[-1]), profit=float(eq.iloc[-1] - init),
                profit_pct=float(eq.iloc[-1] / init - 1.0),
                cagr=float((eq.iloc[-1] / init) ** (1.0 / years) - 1.0),
                sharpe=float(np.sqrt(periods_per_year) * r.mean() / r.std()) if r.std() > 0 else 0.0,
                maxdd=float(dd.min()), eq=eq)


def _period(eq, freq):
    out = []
    for dt, s in eq.groupby(pd.Grouper(freq=freq)):
        if len(s) < 2:
            continue
        out.append(dict(period=str(dt.date()), start=float(s.iloc[0]), end=float(s.iloc[-1]),
                        profit=float(s.iloc[-1] - s.iloc[0]), return_pct=float(s.iloc[-1] / s.iloc[0] - 1.0)))
    return out


def _path_exit(day_ohlc, entry_i, pos, sl, tp):
    path = day_ohlc.iloc[entry_i:]
    if len(path) == 0:
        return 0.0, 'none', None, None
    entry_time = path.index[0]
    entry = float(path['open'].iloc[0])
    for ts, row in path.iterrows():
        if pos > 0:
            adverse = float(row['low'] / entry - 1.0)
            favourable = float(row['high'] / entry - 1.0)
        else:
            adverse = float(entry / row['high'] - 1.0)
            favourable = float(entry / row['low'] - 1.0)
        stop_hit = adverse <= -sl
        tp_hit = favourable >= tp
        if stop_hit and tp_hit:
            return -sl, 'both_stop_first', entry_time, ts
        if stop_hit:
            return -sl, 'stop', entry_time, ts
        if tp_hit:
            return tp, 'tp', entry_time, ts
    close = float(path['close'].iloc[-1])
    gross = (close / entry - 1.0) if pos > 0 else (entry / close - 1.0)
    return gross, 'close', entry_time, path.index[-1]


def simulate(leverage):
    df_1h, comp_hourly, _ = build_daily_geometry()
    ohlc = fetch_futures_ohlcv()
    # Keep only common window where geometry exists.
    ohlc = ohlc[(ohlc.index >= comp_hourly.dropna().index.min()) & (ohlc.index <= comp_hourly.dropna().index.max())].copy()

    idx = df_1h.index
    train_1h = (idx >= TRAIN_START) & (idx < TEST_START)
    train_idx = np.where(train_1h)[0]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[train_idx[-CALIB_BARS:]] = True

    th_hourly = float(comp_hourly[calib_mask].abs().dropna().quantile(Q_HOURLY))
    daily_sig = comp_hourly.groupby(comp_hourly.index.normalize()).last()
    ret_daily = ohlc['close'].pct_change().fillna(0.0).groupby(ohlc.index.normalize()).sum()
    days = pd.Index(sorted(ret_daily.index.unique()))
    calib_days = days[(days >= pd.Timestamp(TRAIN_START)) & (days < pd.Timestamp(TEST_START))]
    test_days = days[days >= pd.Timestamp(TEST_START)]
    daily_vol = float(ret_daily.reindex(calib_days).std())
    th_daily = float(daily_sig.reindex(calib_days).abs().dropna().quantile(Q_DAILY))
    sl = SL_SIGMA * daily_vol
    tp = TP_SIGMA * daily_vol

    rows = []
    counts = {'trades': 0, 'long': 0, 'short': 0, 'stop': 0, 'tp': 0, 'both_stop_first': 0, 'close': 0, 'no_daily_gate': 0, 'no_hourly_entry': 0}
    trade_log = []
    for day in test_days:
        prev_day = day - pd.Timedelta(days=1)
        ds = daily_sig.get(prev_day, np.nan)
        if not np.isfinite(ds) or abs(ds) < th_daily:
            rows.append((day, 0.0)); counts['no_daily_gate'] += 1; continue
        daily_pos = 1.0 if ds > 0 else -1.0
        day_ohlc = ohlc[ohlc.index.normalize() == day]
        if len(day_ohlc) == 0:
            rows.append((day, 0.0)); counts['no_hourly_entry'] += 1; continue
        entry_i = None
        for i, ts in enumerate(day_ohlc.index):
            hs = comp_hourly.get(ts - pd.Timedelta(hours=1), np.nan)
            if np.isfinite(hs) and abs(hs) >= th_hourly and np.sign(hs) == daily_pos:
                entry_i = i
                break
        if entry_i is None:
            rows.append((day, 0.0)); counts['no_hourly_entry'] += 1; continue
        gross, reason, entry_time, exit_time = _path_exit(day_ohlc, entry_i, daily_pos, sl, tp)
        net = gross - RT_COST - FUND_DAY
        rows.append((day, leverage * net))
        counts['trades'] += 1
        counts['long' if daily_pos > 0 else 'short'] += 1
        counts[reason] += 1
        trade_log.append(dict(day=str(day.date()), side='LONG' if daily_pos > 0 else 'SHORT', entry_time=str(entry_time),
                              exit_time=str(exit_time), gross_return=gross, net_return=net, levered_return=leverage*net,
                              exit_reason=reason, daily_signal=float(ds)))
    r = pd.Series(dict(rows)).sort_index()
    m = _equity(r)
    return dict(leverage=leverage, q_daily=Q_DAILY, q_hourly=Q_HOURLY, sl_sigma=SL_SIGMA, tp_sigma=TP_SIGMA,
                daily_threshold=th_daily, hourly_threshold=th_hourly, daily_vol=daily_vol,
                sl_return=sl, tp_return=tp, metrics={k:v for k,v in m.items() if k != 'eq'},
                counts=counts, yearly=_period(m['eq'], 'Y'), quarterly=_period(m['eq'], 'Q'), trade_log=trade_log[:50])


def main():
    t0 = time.time()
    print('='*100)
    print('  INTEGRATED ENTERPRISE SIMULATION — DAILY RISK + 2H/HOURLY ENTRY + TRUE OHLC STOPS')
    print('='*100)
    results = [simulate(2.0), simulate(5.0)]
    out = {'results': results, 'elapsed_seconds': time.time() - t0}
    OUT.write_text(json.dumps(out, indent=2, default=float))
    for r in results:
        m = r['metrics']; c = r['counts']
        print(f"\n  K={r['leverage']:.1f}  final=${m['final']:,.2f} profit=${m['profit']:,.2f} return={m['profit_pct']:.1%} CAGR={m['cagr']:.1%} Sharpe={m['sharpe']:+.2f} MaxDD={m['maxdd']:.1%}")
        print(f"  trades={c['trades']} long={c['long']} short={c['short']} stop={c['stop']} tp={c['tp']} close={c['close']} both={c['both_stop_first']} no_daily={c['no_daily_gate']} no_hourly={c['no_hourly_entry']}")
        print('  yearly:')
        for y in r['yearly']:
            print(f"    {y['period']}: start=${y['start']:,.2f} end=${y['end']:,.2f} profit=${y['profit']:,.2f} ret={y['return_pct']:.1%}")
    print(f"\n  saved -> {OUT}\n  elapsed={time.time()-t0:.1f}s")
    print('='*100)


if __name__ == '__main__':
    main()
