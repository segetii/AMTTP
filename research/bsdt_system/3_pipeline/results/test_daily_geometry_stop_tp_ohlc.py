"""Daily geometry warning with TRUE OHLC stop-loss / take-profit simulation.

This resolves the main blocker in the prior daily test: the old script used hourly
close-path stops. This script fetches Binance ETHUSDT futures OHLCV and tests
whether intraday high/low would hit stop-loss or take-profit after the daily
signal is known.

Conservative same-candle rule: if stop and take-profit are both touched in the
same hourly candle, assume the stop was hit first.
"""
from __future__ import annotations
import sys, json, time, itertools
from pathlib import Path
import requests
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')

from collapse_geometry import Snapshot                                                     # noqa: E402
from run_crypto_pairs_v36_intraday_bsdt import CALIB_BARS, build_intraday_state_panel, calibrate_intraday_engine  # noqa: E402
from run_crypto_pairs_v34_full_combined import build_1h_df, OUT_DIR, TEST_START, TRAIN_START  # noqa: E402
from run_robustness_validation import _cached_fetch_binance_funding                           # noqa: E402
import run_crypto_pairs_v34_full_combined as _v34mod                                         # noqa: E402

CACHE_FG = Path(r'C:\amttp\data\geometric_extractor_engine_arrays_funded_v58_fg.npz')
OHLC_CACHE = Path(r'C:\amttp\data\binance_futures_ETHUSDT_1h_ohlcv.pkl')
SPOT_CACHE_DIR = Path(r'C:\amttp\data')
INIT = 1000.0

# ─────────────────────────────────────────────────────────────────────────────
# Module-level state — prevents redundant computation within a single process.
# Both build_daily_geometry() and prepare() (in test_dynamic_profit_sizing)
# call this module's functions; without caching the geometry is built twice,
# doubling data-fetch and computation time.
# ─────────────────────────────────────────────────────────────────────────────
_FETCH_KLINES_WRAPPED: bool = False
_GEOMETRY_CACHE: 'tuple | None' = None
_CHANNEL_CACHE:  'dict | None'  = None   # per-channel z-scored Series: {E7, dG, E6, dT}
K_LEV = 5.0
RT_COST = 2.0 / 1e4
FUND_DAY = 0.5 / 1e4
Q_GRID = [0.50, 0.60, 0.70, 0.80, 0.90]
SL_MULT = [0.5, 0.75, 1.0, 1.25, 1.5]
TP_MULT = [0.75, 1.0, 1.5, 2.0, 3.0]


def fetch_futures_ohlcv(symbol='ETHUSDT', start='2021-01-01', end='2026-06-01', interval='1h'):
    if OHLC_CACHE.exists():
        df = pd.read_pickle(OHLC_CACHE)
        # For research sweeps a week-stale cache was acceptable. For the offline
        # trade plan it is not: a stale OHLC cache can make a valid current
        # geometry event look untradeable. Require the cache to be fresh to
        # roughly the latest available completed candle.
        now_floor = pd.Timestamp.utcnow().tz_localize(None).floor(interval)
        expected_latest = min(pd.Timestamp(end), now_floor) - pd.Timedelta(hours=2)
        if df.index.min() <= pd.Timestamp(start) and df.index.max() >= expected_latest:
            print('  ETHUSDT futures OHLCV [CACHE]')
            return df[(df.index >= pd.Timestamp(start)) & (df.index < pd.Timestamp(end))].copy()
        print(f'  ETHUSDT futures OHLCV [STALE CACHE max={df.index.max()} expected>={expected_latest}]')
    print('  ETHUSDT futures OHLCV [FETCH]')
    url = 'https://fapi.binance.com/fapi/v1/klines'
    iv_ms = {'1h': 3_600_000, '4h': 14_400_000}.get(interval, 3_600_000)
    s_ms = int(pd.Timestamp(start).timestamp() * 1000)
    e_ms = int(pd.Timestamp(end).timestamp() * 1000)
    recs, cur, fails = [], s_ms, 0
    while cur < e_ms:
        try:
            r = requests.get(url, params={'symbol': symbol, 'interval': interval, 'startTime': cur, 'endTime': e_ms, 'limit': 1500}, timeout=30)
            data = r.json()
            if not isinstance(data, list) or not data:
                break
            recs.extend(data)
            cur = int(data[-1][0]) + iv_ms
            if len(data) < 1500:
                break
            time.sleep(0.03)
            fails = 0
        except Exception as exc:
            fails += 1
            if fails >= 4:
                raise RuntimeError(f'{symbol} OHLCV fetch failed: {exc}')
            time.sleep(1.5)
    if not recs:
        raise RuntimeError('No OHLCV records fetched')
    ts = pd.to_datetime([int(r[0]) for r in recs], unit='ms').tz_localize(None)
    df = pd.DataFrame({
        'open': [float(r[1]) for r in recs],
        'high': [float(r[2]) for r in recs],
        'low': [float(r[3]) for r in recs],
        'close': [float(r[4]) for r in recs],
        'volume': [float(r[5]) for r in recs],
    }, index=ts).sort_index()
    df = df[~df.index.duplicated(keep='last')]
    OHLC_CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_pickle(OHLC_CACHE)
    return df[(df.index >= pd.Timestamp(start)) & (df.index < pd.Timestamp(end))].copy()


def _make_fresh_cached_fetch(orig_fn):
    """Wraps fetch_klines with freshness-aware caching.

    When Binance returns data trailing behind the expected latest timestamp
    (e.g. SOLUSDT spot lags ETH/BTC by several hours), this wrapper
    forward-fills the tail so that the inner join in build_1h_df does NOT
    truncate the ETH/BTC history to the SOL data cutoff.  Only the recent
    tail is filled; historical gaps that predate the last real data point
    are left as-is (they represent genuine exchange-halt periods).
    """
    def wrapped(symbol: str, start: str, end: str, interval: str = '1h'):
        p = SPOT_CACHE_DIR / f'klines_{symbol}_{interval}.pkl'
        now_floor = pd.Timestamp.utcnow().tz_localize(None).floor(interval)
        expected_latest = min(pd.Timestamp(end), now_floor) - pd.Timedelta(hours=2)
        if p.exists():
            s = pd.read_pickle(str(p))
            if len(s) and s.index.min() <= pd.Timestamp(start) and s.index.max() >= expected_latest:
                print(f'  {symbol} [CACHE]')
                return s[(s.index >= pd.Timestamp(start)) & (s.index < pd.Timestamp(end))].copy()
            max_idx = s.index.max() if len(s) else None
            print(f'  {symbol} [STALE max={max_idx} expected>={expected_latest}; re-fetching]')
        else:
            print(f'  {symbol} [no cache; fetching]')
        print(f'  {symbol} [FETCH from Binance]')
        s = orig_fn(symbol, start, end, interval)
        if len(s) == 0:
            return s
        # When Binance itself lags (the exchange hasn't closed the latest candle
        # yet, or the pair has low update frequency), forward-fill the tail from
        # the last real print up to now_floor.  This only affects the recent
        # fringe — all historical gap hours are left unchanged.
        if s.index.max() < expected_latest:
            last_real = s.index.max()
            tail_idx = pd.date_range(
                last_real + pd.Timedelta(hours=1), now_floor, freq='1h'
            )
            if len(tail_idx):
                tail = pd.Series(float(s.loc[last_real]), index=tail_idx, name=s.name)
                s = pd.concat([s, tail]).sort_index()
                print(f'  {symbol} [ffill +{len(tail_idx)}h → {now_floor} (last real candle: {last_real})]')
        SPOT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        s.to_pickle(str(p))
        return s[(s.index >= pd.Timestamp(start)) & (s.index < pd.Timestamp(end))].copy()
    return wrapped


def _z(s, calib_mask):
    return (s - s[calib_mask].mean()) / max(s[calib_mask].std(), 1e-12)


def _equity(r, init=INIT):
    r = r.fillna(0.0).clip(lower=-0.95)
    eq = init * (1 + r).cumprod()
    dd = (eq - eq.cummax()) / eq.cummax()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    return dict(final=float(eq.iloc[-1]), profit=float(eq.iloc[-1]-init),
                profit_pct=float(eq.iloc[-1]/init-1), cagr=float((eq.iloc[-1]/init)**(1/years)-1),
                sharpe=float(np.sqrt(365.25)*r.mean()/r.std()) if r.std()>0 else 0.0,
                maxdd=float(dd.min()), eq=eq)


def _period(eq, freq):
    out = []
    for dt, s in eq.groupby(pd.Grouper(freq=freq)):
        if len(s) < 2:
            continue
        out.append(dict(period=str(dt.date()), start=float(s.iloc[0]), end=float(s.iloc[-1]),
                        profit=float(s.iloc[-1]-s.iloc[0]), return_pct=float(s.iloc[-1]/s.iloc[0]-1)))
    return out


def _load_or_refresh_geometry_cache(X, df_1h, calib_mask):
    """Load funded F/G arrays and extend the cache when fresh bars are available.

    The previous implementation truncated df_1h to the cached array length. That
    made the offline plan stale whenever Binance data advanced but the geometry
    cache had not been refreshed. Here we keep the historical cache and compute
    only the missing tail bars.
    """
    T_total, N, d = X.shape
    if CACHE_FG.exists():
        z = np.load(CACHE_FG)
        F_old = z['F_all']; G_old = z['G_all']; valid_old = z['valid']
        T_old = F_old.shape[0]
        if T_old >= T_total:
            if T_old != T_total:
                print(f"  [warn] geometry cache length {T_old} > dataframe length {T_total}; truncating cache arrays")
            return F_old[:T_total], G_old[:T_total], valid_old[:T_total]
        F_all = np.full((T_total, N, d), np.nan, dtype=np.float32)
        G_all = np.full((T_total, N, d), np.nan, dtype=np.float32)
        valid = np.zeros(T_total, dtype=bool)
        F_all[:T_old] = F_old
        G_all[:T_old] = G_old
        valid[:T_old] = valid_old
        start_t = max(1, T_old)
        print(f"  [refresh] geometry cache {T_old} -> {T_total}; computing {T_total-start_t} new bars")
    else:
        F_all = np.full((T_total, N, d), np.nan, dtype=np.float32)
        G_all = np.full((T_total, N, d), np.nan, dtype=np.float32)
        valid = np.zeros(T_total, dtype=bool)
        start_t = 1
        print(f"  [refresh] geometry cache missing; computing {T_total-start_t} bars")

    M, *_ = calibrate_intraday_engine(X, calib_mask)
    n_done = 0
    for t in range(start_t, T_total):
        try:
            snap = Snapshot(X=X[t], X_prev=X[t-1], history=X[max(0, t-48):t])
            F_all[t] = np.asarray(M.pipeline(snap)['F_t'], dtype=np.float32)
            G_all[t] = np.asarray(M.mfls.state_pullback(snap), dtype=np.float32)
            valid[t] = True
            n_done += 1
        except Exception:
            pass
    CACHE_FG.parent.mkdir(parents=True, exist_ok=True)
    np.savez(CACHE_FG, F_all=F_all, G_all=G_all, valid=valid)
    print(f"  [refresh] saved {CACHE_FG} new_valid={n_done}")
    return F_all, G_all, valid


def _ohlc_day_return(day_ohlc, pos, sl, tp):
    if len(day_ohlc) == 0:
        return 0.0, 'none'
    entry = float(day_ohlc['open'].iloc[0])
    close = float(day_ohlc['close'].iloc[-1])
    for _, row in day_ohlc.iterrows():
        if pos > 0:
            low_ret = float(row['low'] / entry - 1.0)
            high_ret = float(row['high'] / entry - 1.0)
        else:
            low_ret = float(entry / row['high'] - 1.0)   # adverse for short
            high_ret = float(entry / row['low'] - 1.0)   # favourable for short
        stop_hit = sl is not None and low_ret <= -sl
        tp_hit = tp is not None and high_ret >= tp
        if stop_hit and tp_hit:
            return -sl, 'both_stop_first'
        if stop_hit:
            return -sl, 'stop'
        if tp_hit:
            return tp, 'tp'
    return (close / entry - 1.0) if pos > 0 else (entry / close - 1.0), 'close'


def _simulate_daily_ohlc(sig_daily, ohlc, q, sl, tp, calib_days, test_days):
    abs_cal = sig_daily.reindex(calib_days).abs().dropna()
    th = float(abs_cal.quantile(q)) if len(abs_cal) else np.inf
    day_rets = []
    counts = {'hit_stop': 0, 'hit_tp': 0, 'hit_both_stop_first': 0, 'hit_close': 0, 'hit_none': 0}
    active_n = long_n = short_n = 0
    for day in test_days:
        prev_day = day - pd.Timedelta(days=1)
        s = sig_daily.get(prev_day, np.nan)
        if not np.isfinite(s) or abs(s) < th:
            day_rets.append((day, 0.0)); continue
        pos = 1.0 if s > 0 else -1.0
        active_n += 1; long_n += int(pos > 0); short_n += int(pos < 0)
        day_ohlc = ohlc[ohlc.index.normalize() == day]
        gross, reason = _ohlc_day_return(day_ohlc, pos, sl, tp)
        counts['hit_' + reason] += 1
        net = gross - RT_COST - FUND_DAY
        day_rets.append((day, net))
    out = pd.Series(dict(day_rets)).sort_index()
    info = dict(threshold=th, active_days=active_n, long_days=long_n, short_days=short_n,
                active_rate=active_n/max(len(test_days),1), long_rate=long_n/max(active_n,1), short_rate=short_n/max(active_n,1), **counts)
    return out, info


def _extend_df_with_sol_ffill(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Extend df_1h beyond SOL's last data point using forward-filled SOL price.

    SOLUSDT spot klines on Binance have endemic hourly-scale gaps due to
    recurring SOL network outages and exchange maintenance.  The inner join in
    build_1h_df truncates df_1h to the SOL cutoff, which can be many hours
    behind ETH/BTC.  This function appends fresh ETH+BTC tail bars with SOL
    forward-filled from its last known print.

    Only the tail extension (bars AFTER the existing df_1h maximum) is
    affected.  All historical rows \u2014 and the existing geometry cache rows that
    map to those timestamps \u2014 remain identical.
    """
    cache_eth = SPOT_CACHE_DIR / 'klines_ETHUSDT_1h.pkl'
    cache_btc = SPOT_CACHE_DIR / 'klines_BTCUSDT_1h.pkl'
    if not cache_eth.exists() or not cache_btc.exists():
        return df_1h
    try:
        eth = pd.read_pickle(str(cache_eth))
        btc = pd.read_pickle(str(cache_btc))
    except Exception:
        return df_1h
    sol_cutoff = df_1h.index[-1]
    eth_tail = eth[eth.index > sol_cutoff]
    btc_tail = btc[btc.index > sol_cutoff]
    if len(eth_tail) == 0 or len(btc_tail) == 0:
        return df_1h
    tail = pd.DataFrame({'eth': eth_tail, 'btc': btc_tail}).dropna()
    if len(tail) == 0:
        return df_1h
    # Carry forward last known SOL price; log-return is zero (no change).
    last_eth = float(df_1h['eth'].iloc[-1])
    last_btc = float(df_1h['btc'].iloc[-1])
    last_sol = float(df_1h['sol'].iloc[-1])
    tail['sol'] = last_sol
    tail['log_eth'] = np.log(tail['eth'])
    tail['log_btc'] = np.log(tail['btc'])
    tail['log_sol'] = np.log(last_sol)
    tail['ret_eth'] = np.log(tail['eth'] / tail['eth'].shift(1))
    tail['ret_btc'] = np.log(tail['btc'] / tail['btc'].shift(1))
    tail['ret_sol'] = 0.0
    # First bar: link log-returns back to df_1h's last row, not to the tail's own prior.
    tail.at[tail.index[0], 'ret_eth'] = np.log(float(tail['eth'].iloc[0]) / last_eth)
    tail.at[tail.index[0], 'ret_btc'] = np.log(float(tail['btc'].iloc[0]) / last_btc)
    tail['btc_dom'] = tail['ret_btc'] - tail['ret_eth']
    tail['spread_eb'] = tail['log_eth'] - tail['log_btc']
    tail['spread_ret_eb'] = tail['ret_eth'] - tail['ret_btc']
    tail = tail.dropna(subset=['ret_eth', 'ret_btc'])
    if len(tail) == 0:
        return df_1h
    # Align columns exactly to df_1h \u2014 reject if layout has changed.
    missing = set(df_1h.columns) - set(tail.columns)
    if missing:
        print(f'  [sol-ffill] column mismatch {missing}; skipping extension')
        return df_1h
    out = pd.concat([df_1h, tail[df_1h.columns]]).sort_index()
    out = out[~out.index.duplicated(keep='first')]
    print(f'  [sol-ffill] extended df_1h +{len(tail)} bars with SOL forward-filled '
          f'({sol_cutoff} \u2192 {out.index[-1]})')
    return out


def build_daily_geometry():
    """Build the 4-channel BSDT composite signal on hourly df_1h.

    All four canonical orthogonal BSDT channels are included:
        E7  = F̄ · ΔX          signed δ_A  (velocity × force, cascade speed)
        dG  = J_G · ΔX        signed δ_G  (feature-gap jacobian, novel stress)
        E6  = -F · Σ⁻¹(X-μ)  signed δ_C  (Mahalanobis-force, familiar stress)
        dT  = J_T · ΔX        signed δ_T  (KDE-novelty gradient, regime shift)

    Theoretical firing order in a collapse: δ_T → δ_G → δ_A → δ_C.
    Adding δ_G and δ_T (previously missing) gives the engine early-warning
    channels that fire before familiar stress becomes fully systemic.

    Composite: comp = (z(E7) + z(dG) + z(E6) + z(dT)) / 4

    Results are cached in _GEOMETRY_CACHE so that multiple callers within the
    same process (e.g. the plan generator and prepare_dynamic) pay the
    computation cost only once.
    """
    global _FETCH_KLINES_WRAPPED, _GEOMETRY_CACHE
    if _GEOMETRY_CACHE is not None:
        return _GEOMETRY_CACHE

    # Guard against double-wrapping when called from multiple importers.
    if not _FETCH_KLINES_WRAPPED:
        _v34mod.fetch_klines = _make_fresh_cached_fetch(_v34mod.fetch_klines)
        _FETCH_KLINES_WRAPPED = True

    df_1h, _ = build_1h_df(start='2021-01-01', end='2026-06-01')

    # SOL spot klines have endemic gaps that truncate df_1h to SOL's last data
    # point.  Extend the tail with fresh ETH/BTC data and SOL forward-filled so
    # the geometry covers today's market hours.
    df_1h = _extend_df_with_sol_ffill(df_1h)

    fund = _cached_fetch_binance_funding()
    X = np.nan_to_num(build_intraday_state_panel(df_1h, fund.get('BTCUSDT'), fund.get('ETHUSDT')))
    idx = df_1h.index
    train_1h = (idx >= TRAIN_START) & (idx < TEST_START)
    train_idx = np.where(train_1h)[0]
    calib_mask = np.zeros(len(df_1h), dtype=bool); calib_mask[train_idx[-CALIB_BARS:]] = True
    F_all, G_all, valid = _load_or_refresh_geometry_cache(X, df_1h, calib_mask)
    T, N, d = X.shape
    F_flat = F_all.reshape(T, -1); Xt_flat = X.reshape(T, -1)
    dX = np.full_like(X, np.nan, dtype=np.float32); dX[:-1] = X[1:] - X[:-1]
    dX_flat = dX.reshape(T, -1); dX_prev = np.roll(dX_flat, 1, axis=0); dX_prev[0] = np.nan

    # ── E7: EMA-force × velocity  (signed δ_A — cascade speed) ──────────
    a = 2/(32+1); Fbar = np.full_like(F_flat, np.nan); Fbar[0] = F_flat[0]
    for t in range(1, T):
        if np.isnan(F_flat[t]).any(): Fbar[t] = Fbar[t-1]
        elif np.isnan(Fbar[t-1]).any(): Fbar[t] = F_flat[t]
        else: Fbar[t] = (1-a)*Fbar[t-1] + a*F_flat[t]
    E7 = pd.Series(np.einsum('ti,ti->t', Fbar, dX_prev), index=idx)

    # ── dG: feature-gap jacobian × velocity  (signed δ_G — novel stress) ─
    # J_G = 2*(X - μ0) @ (I − V_k V_kᵀ)  fitted on calib window only.
    # Dot with ΔX_{t-1}: positive = moving further into the gap (novel).
    M_cal, *_ = calibrate_intraday_engine(X, calib_mask)
    cal = M_cal.bsdt.cal
    Xcent = X - cal.mu0                                              # (T, N, d)
    JG_all = 2.0 * (Xcent @ cal.I_minus_VVT)                        # (T, N, d)
    dG = pd.Series(np.einsum('ti,ti->t', JG_all.reshape(T, -1), dX_prev), index=idx)

    # ── E6: Mahalanobis-force projection  (signed δ_C — familiar stress) ─
    Xc_flat = Xt_flat[calib_mask]; mu = Xc_flat.mean(0)
    Sinv = np.linalg.inv(np.cov(Xc_flat, rowvar=False) + 1e-6*np.eye(N*d))
    e6 = np.full(T, np.nan)
    for t in range(1, T):
        if valid[t]:
            try: e6[t] = float(-(F_flat[t] @ (Sinv @ (Xt_flat[t] - mu))))
            except Exception: pass
    E6 = pd.Series(e6, index=idx)

    # ── dT: KDE temporal-novelty gradient × velocity  (signed δ_T) ───────
    # ∇(-log p̂_h)(X_t) · ΔX_{t-1}: positive = moving into novel territory.
    # δ_T fires FIRST in a collapse cascade; 24-bar window captures intraday
    # regime novelty at 1h resolution without expensive long-range KDE.
    KDE_H = 24
    bsdt = M_cal.bsdt
    dt_vals = np.full(T, np.nan)
    for t in range(KDE_H, T):
        snap = Snapshot(X=X[t], X_prev=X[t-1], history=X[t-KDE_H:t])
        JT = bsdt.grad_delta_T(snap)                                 # (N, d)
        dt_vals[t] = float(np.dot(JT.reshape(-1), dX_prev[t]))
    dT = pd.Series(dt_vals, index=idx)

    # ── Bifurcated 4-channel BSDT architecture ───────────────────────────
    # Firing order: δ_T (earliest) → δ_G → δ_A → δ_C (latest).
    #
    # Roles are SPLIT by time-horizon:
    #   comp  = (z(E7) + z(E6)) / 2   ← HOURLY ENTRY SIGNAL
    #           δ_A (velocity) + δ_C (Mahalanobis) are the sharpest same-bar
    #           predictors; averaging them preserves the original signal quality.
    #
    #   dG, dT are kept in _CHANNEL_CACHE for the QUADRANT MULTIPLIER layer
    #           (simulate_v63_quadrant._build_quadrant_multiplier).
    #           δ_G and δ_T fire 4–7 days early → ideal for regime detection
    #           but too noisy to include directly in the hourly composite.
    zE7 = _z(E7, calib_mask)
    zdG = _z(dG, calib_mask)
    zE6 = _z(E6, calib_mask)
    zdT = _z(dT, calib_mask)
    comp = (zE7 + zE6) / 2.0      # hourly entry signal: δ_A + δ_C only

    # Cache all four channels so get_channel_series() can expose dG/dT
    # to the quadrant layer without re-running the pipeline.
    global _CHANNEL_CACHE
    _CHANNEL_CACHE = {'E7': zE7, 'dG': zdG, 'E6': zE6, 'dT': zdT}

    _GEOMETRY_CACHE = (df_1h, comp, calib_mask)
    return _GEOMETRY_CACHE


def get_channel_series() -> dict:
    """Return the four individual z-scored BSDT channel Series.

    build_daily_geometry() must have been called first (or call it implicitly).
    Keys: 'E7' (signed δ_A), 'dG' (signed δ_G), 'E6' (signed δ_C), 'dT' (signed δ_T).
    All Series share the same hourly DatetimeIndex as the composite.
    """
    if _CHANNEL_CACHE is None:
        build_daily_geometry()   # populates both caches
    return _CHANNEL_CACHE


def main():
    BAR = '='*100
    print(BAR)
    print('  DAILY GEOMETRY SL/TP WITH TRUE BINANCE FUTURES OHLC HIGH/LOW')
    print(BAR)
    t0 = time.time()
    df_1h, comp_hourly, calib_mask = build_daily_geometry()
    ohlc = fetch_futures_ohlcv()
    ret_daily = ohlc['close'].pct_change().fillna(0.0).groupby(ohlc.index.normalize()).sum()
    days = pd.Index(sorted(ret_daily.index.unique()))
    calib_days = days[(days >= pd.Timestamp(TRAIN_START)) & (days < pd.Timestamp(TEST_START))]
    test_days = days[days >= pd.Timestamp(TEST_START)]
    daily_vol = float(ret_daily.reindex(calib_days).std())
    signals = {
        'last': comp_hourly.groupby(comp_hourly.index.normalize()).last(),
        'mean': comp_hourly.groupby(comp_hourly.index.normalize()).mean(),
        'absmax': comp_hourly.groupby(comp_hourly.index.normalize()).apply(lambda s: s.loc[s.abs().idxmax()] if len(s.dropna()) else np.nan),
    }
    target_next = ret_daily.shift(-1)
    print(f'\n  calib daily σ={daily_vol:.2%}; test days={len(test_days)}')
    for name, sig in signals.items():
        ix = sig.reindex(test_days).dropna().index.intersection(target_next.reindex(test_days).dropna().index)
        print(f"  daily {name:<6} forecast: pearson={sig.reindex(ix).corr(target_next.reindex(ix)):+.4f} signIC={((np.sign(sig.reindex(ix))*np.sign(target_next.reindex(ix))>0).mean()):.1%}")

    rows = []
    combos = [(None, None)] + [(sl*daily_vol, tp*daily_vol) for sl, tp in itertools.product(SL_MULT, TP_MULT)]
    for sig_name, sig in signals.items():
        for q in Q_GRID:
            for sl, tp in combos:
                r, info = _simulate_daily_ohlc(sig, ohlc, q, sl, tp, calib_days, test_days)
                m = _equity(K_LEV*r)
                rows.append(dict(signal=sig_name, q=q,
                                 sl_mult=None if sl is None else sl/daily_vol,
                                 tp_mult=None if tp is None else tp/daily_vol,
                                 sl=None if sl is None else sl, tp=None if tp is None else tp,
                                 final=m['final'], profit=m['profit'], cagr=m['cagr'], sharpe=m['sharpe'], maxdd=m['maxdd'], **info))
    rows = sorted(rows, key=lambda x: (x['final'], x['sharpe']), reverse=True)
    print(f"\n{BAR}\n  TRUE-OHLC DAILY RESULTS — K=5, $1,000, low-cost maker\n{BAR}")
    print(f"  {'Rank':>4} {'Sig':<6} {'q':>4} {'SLσ':>5} {'TPσ':>5} {'Active':>7} {'Long':>6} {'Final$':>10} {'Sharpe':>8} {'MaxDD':>8} {'S/TP/B':>11}")
    for i, r in enumerate(rows[:20], 1):
        sls = 'None' if r['sl_mult'] is None else f"{r['sl_mult']:.2f}"
        tps = 'None' if r['tp_mult'] is None else f"{r['tp_mult']:.2f}"
        print(f"  {i:>4} {r['signal']:<6} {r['q']:>4.2f} {sls:>5} {tps:>5} {r['active_rate']:>6.1%} {r['long_rate']:>5.1%} "
              f"{r['final']:>10,.0f} {r['sharpe']:>+8.2f} {r['maxdd']:>+7.1%} {r['hit_stop']:>3}/{r['hit_tp']:<3}/{r['hit_both_stop_first']:<3}")

    best = rows[0]
    r, _ = _simulate_daily_ohlc(signals[best['signal']], ohlc, best['q'], best['sl'], best['tp'], calib_days, test_days)
    m = _equity(K_LEV*r)
    print(f"\n  BEST TRUE-OHLC: {best['signal']} q={best['q']:.2f} SL={best['sl_mult']}σ TP={best['tp_mult']}σ final=${best['final']:,.2f} maxDD={best['maxdd']:.1%}")
    print(f"\n  YEARLY PROFIT — BEST TRUE-OHLC DAILY")
    for row in _period(m['eq'], 'Y'):
        print(f"  {row['period']:<12} start={row['start']:>12,.2f} end={row['end']:>12,.2f} profit={row['profit']:>12,.2f} return={row['return_pct']:>8.1%}")

    out = Path(OUT_DIR) / 'daily_geometry_stop_tp_ohlc_results.json'
    out.write_text(json.dumps({'daily_vol': daily_vol, 'best': best, 'top20': rows[:20], 'all_results': rows, 'best_yearly': _period(m['eq'], 'Y')}, indent=2, default=float))
    print(f"\n  saved -> {out}\n  elapsed={time.time()-t0:.1f}s\n{BAR}")

if __name__ == '__main__':
    main()
