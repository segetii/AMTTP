"""
Crypto BSDT v33 — Full 1h/4h History via Binance klines API
============================================================

Fixes v32 issues:
  1. Full Binance klines API (2021-01-01 → now) — no yfinance 729-day cap
     ETH/BTC/SOL/BNB USDT pairs, ~47k bars at 1h (train + test)
  2. Pairs CORRECTED to TREND-FOLLOWING at sub-daily resolution
     At 1h spread momentum, ETH/BTC follows through (not mean-reverts)
  3. Binary daily gate: clean mask (geom>0.5 & kramers_p>0.3) with 1-day lag
     Engine computed EOD day D → trade all bars of day D+1, no look-ahead
  4. Same train/test split as daily (train 2021-22, test 2023+)
  5. 4h version via resample of 1h

Configs:
  [A] 1h UNGATED     — quality-gated strategies, no physics engine gate
  [B] 1h DAY-GATED   — [A] × daily binary activation mask
  [C] 4h UNGATED     — same at 4h resolution
  [D] 4h DAY-GATED   — [C] × daily binary mask
  [E] DAILY ref      — production v28_full_no_brk (2023 → now)
"""
from __future__ import annotations
import os, sys, json, time, warnings
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
from pathlib import Path
import numpy as np
import pandas as pd
import requests
warnings.filterwarnings('ignore')

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from run_crypto_pairs_v19 import (
    fetch_and_prepare, add_cross_market_features,
    fetch_binance_funding, add_leverage_features,
    simulate_from_pnl,
    TRAIN_START, TRAIN_END, TEST_START, OUT_DIR,
)
from run_crypto_pairs_v30_perp_realism import build_book
from run_crypto_pairs_v27 import compute_unsigned_weights, G_LO, K_LO
from run_crypto_pairs_v28 import (
    V28_KEYS, V28_WCOLS,
    build_v28_pnl,
    compute_quality_risk_weights as daily_cqrw,
)

OUT_DIR_ = Path(OUT_DIR)


# ─── helpers ─────────────────────────────────────────────────────────────────

def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


def _ann_factor(bpd: int) -> float:
    return 252.0 * bpd


# ═══════════════════════════════════════════════════════════════════════════
#  1.  BINANCE KLINES FETCH
# ═══════════════════════════════════════════════════════════════════════════

def fetch_binance_klines(symbol: str, start: str, end: str,
                          interval: str = '1h') -> pd.Series:
    """
    Fetch hourly close prices from Binance public klines endpoint.
    Paginates automatically (1000 bars/request).
    Returns tz-naive UTC DatetimeIndex Series.
    """
    url = 'https://api.binance.com/api/v3/klines'
    iv_ms = {'1h': 3_600_000, '4h': 14_400_000}.get(interval, 3_600_000)
    start_ms = int(pd.Timestamp(start).timestamp() * 1000)
    end_ms   = int(pd.Timestamp(end).timestamp() * 1000)

    records, cur, fails = [], start_ms, 0
    while cur < end_ms:
        try:
            r = requests.get(url, params={
                'symbol': symbol, 'interval': interval,
                'startTime': cur, 'endTime': end_ms, 'limit': 1000,
            }, timeout=30)
            data = r.json()
            if not isinstance(data, list) or len(data) == 0:
                break
            records.extend(data)
            cur = int(data[-1][0]) + iv_ms
            if len(data) < 1000:
                break
            time.sleep(0.04)
            fails = 0
        except Exception as exc:
            fails += 1
            if fails >= 4:
                print(f"  [warn] {symbol} klines fetch stopped: {exc}")
                break
            time.sleep(1.5)

    if not records:
        return pd.Series(dtype=float, name=symbol)

    ts   = pd.to_datetime([int(r[0]) for r in records], unit='ms')
    vals = np.array([float(r[4]) for r in records])   # index-4 = close price
    s = pd.Series(vals, index=ts, name=symbol)
    s.index = s.index.tz_localize(None)
    return s.sort_index().drop_duplicates()


def build_intraday_df(start: str = '2021-01-01',
                       end:   str = '2026-05-01') -> pd.DataFrame:
    """
    Fetch 1h OHLCV for ETH+BTC+SOL+BNB from Binance, build feature DataFrame.
    """
    sym_map = {
        'ETHUSDT': 'eth', 'BTCUSDT': 'btc',
        'SOLUSDT': 'sol', 'BNBUSDT': 'bnb',
    }
    prices = {}
    for sym, col in sym_map.items():
        print(f"  {sym} 1h ... ", end='', flush=True)
        s = fetch_binance_klines(sym, start, end)
        if len(s):
            print(f"{len(s):,} bars  ({s.index[0].date()} → {s.index[-1].date()})")
        else:
            print("EMPTY — falling back to yfinance")
            import yfinance as yf
            tk = sym.replace('USDT', '-USD')
            s = yf.download(tk, start=start, progress=False,
                            auto_adjust=True)['Close'].squeeze()
            s.index = s.index.tz_localize(None)
        prices[col] = s

    df = pd.DataFrame(prices).dropna()
    for a in ['eth', 'btc', 'sol', 'bnb']:
        df[f'ret_{a}']  = np.log(df[a] / df[a].shift(1))
        df[f'log_{a}']  = np.log(df[a])
    df['ret_alt_basket'] = (df['ret_eth'] + df['ret_sol'] + df['ret_bnb']) / 3.0
    df['btc_dom'] = df['ret_btc'] - df['ret_alt_basket']
    df = df.dropna()

    n_days = (df.index[-1] - df.index[0]).days
    n_train = int(((df.index >= TRAIN_START) & (df.index < TEST_START)).sum())
    n_test  = int((df.index >= TEST_START).sum())
    print(f"\n  DataFrame: {df.index[0]}  →  {df.index[-1]}   "
          f"n={len(df):,} bars  ({n_days} calendar days)")
    print(f"  Train bars: {n_train:,}   Test bars: {n_test:,}")
    return df


def resample_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Resample 1h DataFrame to 4h (sum returns, last price for price cols)."""
    agg = {}
    price_cols = ['eth', 'btc', 'sol', 'bnb']
    for col in df_1h.columns:
        if col.startswith('ret_') or col == 'btc_dom':
            agg[col] = df_1h[col].resample('4h').sum()
        elif col in price_cols or col.startswith('log_'):
            agg[col] = df_1h[col].resample('4h').last()
    df_4h = pd.DataFrame(agg).dropna()
    # Recompute logs from prices
    for a in ['eth', 'btc', 'sol', 'bnb']:
        if a in df_4h.columns:
            df_4h[f'log_{a}'] = np.log(df_4h[a])
    n_days = (df_4h.index[-1] - df_4h.index[0]).days
    print(f"  4h DataFrame: {df_4h.index[0]}  →  {df_4h.index[-1]}   "
          f"n={len(df_4h):,} bars  (~{n_days} calendar days)")
    return df_4h


# ═══════════════════════════════════════════════════════════════════════════
#  2.  INTRADAY STRATEGY SIGNALS (corrected for sub-daily resolution)
# ═══════════════════════════════════════════════════════════════════════════

def compute_strategies(df: pd.DataFrame, bpd: int) -> dict:
    """
    Compute three intraday strategies at any bar-per-day resolution.

    Key fix vs v32:
      Pairs uses TREND-FOLLOWING on the spread (not mean-reversion).
      At sub-daily resolution, crypto spreads trend; mean-reversion
      loses money (v32 pairs Sharpe was -0.99 with mean-reversion).

    Strategies:
      trend       : sign(3-day cumulative ETH return)           → ETH position
      pairs_trend : sign(3-day cumulative ETH-BTC spread return) → spread position
      macro       : sign(7-day BTC dominance MA)                → BTC vs ETH

    All signals shift(1) before applying to next bar's return (no look-ahead).
    """
    N3  = 3 * bpd    # 3-day equivalent window
    N7  = 7 * bpd    # 7-day equiv

    # ── trend ─────────────────────────────────────────────────────────────
    ret_N = df['ret_eth'].rolling(N3, min_periods=max(N3 // 4, 10)).sum()
    pos_trend = np.sign(ret_N.shift(1)).fillna(0.0)
    pnl_trend = pos_trend * df['ret_eth']

    # ── pairs: TREND-FOLLOWING spread (ETH vs BTC) ────────────────────────
    # 3-day cumulative spread change → follow direction
    spread_ret = df['ret_eth'] - df['ret_btc']
    spread_mom = spread_ret.rolling(N3, min_periods=max(N3 // 4, 10)).sum()
    pos_pairs = np.sign(spread_mom.shift(1)).fillna(0.0)
    pnl_pairs = pos_pairs * spread_ret       # profit when spread continues

    # ── macro: BTC dominance momentum ────────────────────────────────────
    dom_ma = df['btc_dom'].rolling(N7, min_periods=max(N7 // 4, 10)).mean()
    pos_macro = np.sign(dom_ma.shift(1)).fillna(0.0)
    pnl_macro = (pos_macro * df['ret_btc'] + (-pos_macro) * df['ret_eth']) / 2.0

    return {
        'trend':    pnl_trend.fillna(0.0),
        'pairs':    pnl_pairs.fillna(0.0),
        'breakout': pd.Series(0.0, index=df.index),
        'macro':    pnl_macro.fillna(0.0),
    }


# ═══════════════════════════════════════════════════════════════════════════
#  3.  QUALITY WEIGHTS (native bar resolution)
# ═══════════════════════════════════════════════════════════════════════════

def compute_quality(strats: dict, bpd: int,
                     vol_win_d: int = 60,
                     sharpe_win_d: int = 120,
                     sharpe_k: float = 2.0,
                     scale_cap: float = 5.0) -> pd.DataFrame:
    """
    Per-bar quality × vol-scale weights (all scaled by bpd).

    target_vol = 0.01 / sqrt(bpd)  (daily 1% vol target → per-bar equiv)
    Returns DataFrame[T, 4] with V28_KEYS columns, already lagged 1 bar.
    """
    vol_win    = vol_win_d    * bpd
    sharpe_win = sharpe_win_d * bpd
    target_vol = 0.01 / np.sqrt(float(bpd))
    ann        = _ann_factor(bpd)

    out = {}
    for k in V28_KEYS:
        p = strats[k]
        if k == 'breakout':
            out[k] = pd.Series(0.0, index=p.index)
            continue
        rv     = p.rolling(vol_win,    min_periods=bpd * 5).std().clip(lower=1e-9)
        rm     = p.rolling(sharpe_win, min_periods=bpd * 10).mean()
        rs     = p.rolling(sharpe_win, min_periods=bpd * 10).std().clip(lower=1e-9)
        rsharpe = (rm / rs) * np.sqrt(ann)
        q      = _sigmoid(rsharpe.fillna(0.0) * sharpe_k)
        scale  = (target_vol / rv).clip(upper=scale_cap)
        out[k] = (q * scale).shift(1).fillna(0.0)

    return pd.DataFrame(out)


# ═══════════════════════════════════════════════════════════════════════════
#  4.  PORTFOLIO ASSEMBLY
# ═══════════════════════════════════════════════════════════════════════════

def assemble(strats: dict, Q: pd.DataFrame,
             gate: pd.Series | None = None) -> pd.Series:
    """
    Row-normalize quality weights, multiply by strategies.
    gate: boolean Series aligned to Q.index (None = ungated).
    Q is already 1-bar shifted; strats[k] uses shift(1) internally.
    """
    eff = Q[V28_KEYS].copy()
    row_sum = eff.sum(axis=1).replace(0.0, np.nan)
    eff = eff.div(row_sum, axis=0).fillna(0.0)

    pnl = pd.Series(0.0, index=Q.index)
    for k in V28_KEYS:
        pnl = pnl + eff[k] * strats[k]

    if gate is not None:
        g = gate.astype(float).reindex(pnl.index, fill_value=0.0)
        pnl = pnl * g

    return pnl


# ═══════════════════════════════════════════════════════════════════════════
#  5.  DAILY GATE → BINARY BAR MASK
# ═══════════════════════════════════════════════════════════════════════════

def build_binary_gate(F_daily: pd.DataFrame,
                       df_intra: pd.DataFrame,
                       g_lo: float = G_LO,
                       k_lo: float = K_LO) -> pd.Series:
    """
    Build a boolean Series on df_intra.index.

    Engine gate from daily physics engine (EOD day D):
      active[D] = (geom_score[D] > g_lo) & (kramers_p[D] > k_lo)

    Execution with 1-day lag (no look-ahead):
      gate[bar on day D] = active[D-1]
      → trade on day D based on yesterday's engine signal

    Handles daily index with potential tz  vs tz-naive 1h index.
    """
    geom_n = F_daily['geom_score'].fillna(0.0)
    kp     = F_daily['kramers_p'].fillna(0.0)
    active = ((geom_n > g_lo) & (kp > k_lo)).astype(float)
    active_lag = active.shift(1).fillna(0.0)

    # Normalize daily index to tz-naive dates
    idx = pd.to_datetime(active_lag.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    active_lag.index = idx.normalize()

    intra_dates = pd.to_datetime(df_intra.index).normalize()
    d_map = active_lag.to_dict()
    gate = pd.Series(
        [d_map.get(d, 0.0) for d in intra_dates],
        index=df_intra.index, dtype=float,
    )
    return gate.astype(bool)


# ═══════════════════════════════════════════════════════════════════════════
#  6.  EQUITY CURVE + K SWEEP
# ═══════════════════════════════════════════════════════════════════════════

def equity_curve(pnl_gross: pd.Series, K: float, bpd: int, *,
                  init: float = 100.0, tcost_bps: float = 5.0) -> dict:
    """
    Simulate equity at leverage K.

    Fee: 5 bps per active DAY expressed as (5/bpd) bps per active bar.
    CAGR: calendar-days denominator.
    Sharpe: annualized by sqrt(252 × bpd).
    """
    p     = pnl_gross.fillna(0.0) * float(K)
    fee   = (tcost_bps / 1e4 / bpd) * (pnl_gross.fillna(0.0).abs() > 1e-12).astype(float)
    r_net = p - fee
    eq    = init * (1.0 + r_net).cumprod()
    peak  = eq.cummax()
    dd    = (eq - peak) / peak

    cal_d = (pnl_gross.index[-1] - pnl_gross.index[0]).total_seconds() / 86400.0
    yrs   = cal_d / 365.0
    final = float(eq.iloc[-1])
    cagr  = float(max(final, 1e-6) / init) ** (1.0 / max(yrs, 1e-9)) - 1.0
    ann   = _ann_factor(bpd)
    sh    = float(r_net.mean() / r_net.std() * np.sqrt(ann)) if r_net.std() > 0 else 0.0
    act_d = float((r_net.abs() > 1e-12).sum()) / bpd

    return {
        'K': float(K), 'final': float(final),
        'pnl_dollar': float(final - init),
        'sharpe_net': float(sh), 'cagr': float(cagr),
        'max_dd': float(dd.min()),
        'active_days_eq': float(act_d),
    }


def sweep_K(pnl: pd.Series, bpd: int, tag: str,
            K_vals: list | None = None) -> list:
    if K_vals is None:
        K_vals = [1, 2, 3, 5, 7, 10, 12, 14, 17, 20, 23, 25, 29, 30]
    show   = {1, 2, 5, 10, 14, 20, 25, 29}
    rows   = [equity_curve(pnl, K, bpd) for K in K_vals]
    df_r   = pd.DataFrame(rows)

    print(f"\n  {'K':>3}  {'Final $':>9}  {'CAGR':>7}  "
          f"{'Sharpe':>7}  {'MaxDD':>7}  {'ActvD':>6}")
    for r in rows:
        if r['K'] in show:
            print(f"  {int(r['K']):>3}  ${r['final']:>8.2f}  "
                  f"{100*r['cagr']:+6.1f}%  "
                  f"{r['sharpe_net']:+6.3f}  "
                  f"{100*r['max_dd']:+6.1f}%  "
                  f"{r['active_days_eq']:5.0f}d")

    print(f"\n  Optimal K under DD limits [{tag}]:")
    for label, lim in [('DD<10%',0.10),('DD<20%',0.20),
                        ('DD<30%',0.30),('DD<40%',0.40)]:
        sub = df_r[df_r['max_dd'] > -lim]
        if sub.empty:
            print(f"    {label}: none satisfy constraint")
            continue
        best = sub.sort_values('sharpe_net', ascending=False).iloc[0]
        print(f"    {label}: K={int(best['K'])}  "
              f"${best['final']:.2f}  "
              f"CAGR={100*best['cagr']:+.1f}%  "
              f"Sharpe={best['sharpe_net']:+.3f}")

    return rows


def print_strat_standalone(strats: dict, mask, bpd: int):
    """Print per-strategy standalone Sharpe/CAGR for the test period."""
    ann = _ann_factor(bpd)
    # Accept either a boolean array or a pandas boolean Series
    if not isinstance(mask, pd.Series):
        mask = pd.Series(mask, index=list(strats.values())[0].index)
    print(f"  {'strategy':<12}  {'Sharpe':>8}  {'CAGR':>8}  "
          f"{'MaxDD':>8}  {'actv/tot':>12}  {'hit%':>6}")
    for k in V28_KEYS:
        if k == 'breakout':
            continue
        p  = strats[k][mask].fillna(0.0)
        if p.std() == 0:
            continue
        act = int((p.abs() > 1e-12).sum())
        sh  = float(p.mean() / p.std() * np.sqrt(ann))
        idx = p.index
        yrs = (idx[-1] - idx[0]).days / 365.0
        cagr   = float((1 + p).prod() ** (1 / max(yrs, 1e-9)) - 1)
        eq     = (1 + p).cumprod()
        mdd    = float((eq / eq.cummax() - 1).min())
        hit    = float((p > 0).sum()) / max(act, 1) * 100
        print(f"  {k:<12}  {sh:+8.3f}  {100*cagr:+7.1f}%  "
              f"{100*mdd:+7.1f}%  {act:6,}/{len(p):,}  {hit:5.1f}%")


# ═══════════════════════════════════════════════════════════════════════════
#  7.  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print("=" * 88)
    print("  CRYPTO BSDT v33 — Full Binance 1h/4h History + Corrected Intraday")
    print("  train 2021-22  |  test 2023-2026  |  pairs → trend-following")
    print("=" * 88)

    results = {}

    # ──────────────────────────────────────────────────────────── FETCH ──
    print("\n[1] Fetching full 1h history from Binance klines API ...")
    df_1h = build_intraday_df(start='2021-01-01', end='2026-05-01')

    test_mask_1h  = df_1h.index >= TEST_START
    train_mask_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)

    print(f"\n  Rebasing to 4h ...")
    df_4h = resample_4h(df_1h)
    test_mask_4h  = df_4h.index >= TEST_START

    results['data'] = {
        'n_1h_total': int(len(df_1h)),
        'n_1h_train': int(train_mask_1h.sum()),
        'n_1h_test':  int(test_mask_1h.sum()),
        'n_4h_test':  int(test_mask_4h.sum()),
        'start': str(df_1h.index[0].date()),
        'end':   str(df_1h.index[-1].date()),
    }

    # ──────────────────────────────────────────────────────── STRATEGIES ──
    print("\n[2] Computing intraday strategies ...")
    strats_1h = compute_strategies(df_1h, bpd=24)
    strats_4h = compute_strategies(df_4h, bpd=6)

    print(f"\n  Per-strategy standalone [1h test period 2023 → now]:")
    print_strat_standalone(strats_1h, test_mask_1h, bpd=24)
    print(f"\n  Per-strategy standalone [4h test period 2023 → now]:")
    print_strat_standalone(strats_4h, test_mask_4h, bpd=6)

    # ──────────────────────────────────────────────────────── QUALITY ──
    print("\n[3] Computing quality weights ...")
    Q_1h = compute_quality(strats_1h, bpd=24)
    Q_4h = compute_quality(strats_4h, bpd=6)

    # ──────────────────────────────────────── UNGATED ASSEMBLY [A] [C] ──
    pnl_1h_ug = assemble(strats_1h, Q_1h)[test_mask_1h]
    pnl_4h_ug = assemble(strats_4h, Q_4h)[test_mask_4h]

    ann_1h = _ann_factor(24)
    ann_4h = _ann_factor(6)

    sh_1h_ug = float(pnl_1h_ug.mean() / pnl_1h_ug.std() * np.sqrt(ann_1h))
    sh_4h_ug = float(pnl_4h_ug.mean() / pnl_4h_ug.std() * np.sqrt(ann_4h))
    print(f"\n  Gross Sharpe ungated — 1h: {sh_1h_ug:+.4f}   4h: {sh_4h_ug:+.4f}")

    print("\n" + "─" * 88)
    print("  [A]  1h UNGATED — quality-gated, no physics engine")
    print("─" * 88)
    results['1h_ungated'] = sweep_K(pnl_1h_ug, bpd=24, tag='1h_ungated')

    print("\n" + "─" * 88)
    print("  [C]  4h UNGATED — quality-gated, no physics engine")
    print("─" * 88)
    results['4h_ungated'] = sweep_K(pnl_4h_ug, bpd=6, tag='4h_ungated')

    # ──────────────────────────────────────────── DAILY ENGINE GATE ──
    print("\n[4] Running daily v28 pipeline for physics gate ...")

    daily_ok = False
    try:
        df_d = fetch_and_prepare()
        df_d = add_cross_market_features(df_d)
        funding = fetch_binance_funding(
            symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
        df_d = add_leverage_features(df_d, funding)

        train_mask_d   = (df_d.index >= TRAIN_START) & (df_d.index <= TRAIN_END)
        train_mask_arr = np.asarray(train_mask_d, dtype=bool)
        test_mask_d    = df_d.index >= TEST_START

        strats_d, F_daily, _, _ = build_book(df_d, train_mask_d, train_mask_arr)
        W_d  = compute_unsigned_weights(F_daily, use_activation=True,
                                         g_lo=G_LO, k_lo=K_LO)
        Q_d  = daily_cqrw(strats_d, vol_win=60, sharpe_win=120, sharpe_k=2.0)
        lev_d = pd.Series(1.0, index=df_d.index)
        pnl_d = build_v28_pnl(strats_d, W_d, Q_d, lev_d, df_d.index)
        s_ref = simulate_from_pnl(pnl_d[test_mask_d].fillna(0.0))

        print(f"\n  [E] Daily v28_full_no_brk (2023 → now):")
        print(f"      Sharpe={s_ref['sharpe']:+.4f}  "
              f"CAGR={100*s_ref['cagr']:+.2f}%  "
              f"MaxDD={100*s_ref['max_dd']:+.2f}%  "
              f"Active={int(s_ref['active_days'])}d")
        results['daily_ref'] = {
            'sharpe': float(s_ref['sharpe']),
            'cagr':   float(s_ref['cagr']),
            'max_dd': float(s_ref['max_dd']),
            'active_days': int(s_ref['active_days']),
        }

        # Binary gate for 1h and 4h (test period data)
        print(f"\n[5] Building binary activation gate (geom>{G_LO} & kp>{K_LO}) ...")
        gate_1h = build_binary_gate(F_daily, df_1h[test_mask_1h])
        gate_4h = build_binary_gate(F_daily, df_4h[test_mask_4h])

        act_d_1h = float(gate_1h.sum()) / 24
        act_d_4h = float(gate_4h.sum()) / 6
        print(f"  1h gate: {gate_1h.sum():,} active bars  "
              f"≈ {act_d_1h:.0f} active days  "
              f"(daily active={int(s_ref['active_days'])}d expected)")
        print(f"  4h gate: {gate_4h.sum():,} active bars  "
              f"≈ {act_d_4h:.0f} active days")

        results['gate_active_days_1h'] = float(act_d_1h)
        results['gate_active_days_4h'] = float(act_d_4h)

        # Gated assembly — strategies on full df so quality is warmed up;
        # gate applied only on test-period bars
        gate_1h_full = gate_1h.reindex(df_1h.index, fill_value=False)
        gate_4h_full = gate_4h.reindex(df_4h.index, fill_value=False)

        pnl_1h_g = assemble(strats_1h, Q_1h, gate=gate_1h_full)[test_mask_1h]
        pnl_4h_g = assemble(strats_4h, Q_4h, gate=gate_4h_full)[test_mask_4h]

        sh_1h_g = float(pnl_1h_g.mean() / pnl_1h_g.std() * np.sqrt(ann_1h)) if pnl_1h_g.std() > 0 else 0.0
        sh_4h_g = float(pnl_4h_g.mean() / pnl_4h_g.std() * np.sqrt(ann_4h)) if pnl_4h_g.std() > 0 else 0.0
        print(f"\n  Gross Sharpe gated — 1h: {sh_1h_g:+.4f}   4h: {sh_4h_g:+.4f}")

        print("\n" + "─" * 88)
        print("  [B]  1h DAY-GATED — daily physics gate + intraday quality")
        print("─" * 88)
        results['1h_daygated'] = sweep_K(pnl_1h_g, bpd=24, tag='1h_daygated')

        print("\n" + "─" * 88)
        print("  [D]  4h DAY-GATED — daily physics gate + intraday quality")
        print("─" * 88)
        results['4h_daygated'] = sweep_K(pnl_4h_g, bpd=6, tag='4h_daygated')

        daily_ok = True

    except Exception as exc:
        import traceback
        print(f"\n  [WARNING] Daily engine pipeline failed: {exc}")
        traceback.print_exc()

    # ──────────────────────────────────────────────────────────── SAVE ──
    out_path = OUT_DIR_ / 'crypto_bsdt_v33_intraday_binance.json'
    with open(out_path, 'w') as fh:
        json.dump(results, fh, indent=2, default=float)
    print(f"\n  Saved → {out_path}")

    # ─────────────────────────────────────────── COMPARISON TABLE ──
    print("\n" + "=" * 88)
    print(f"  COMPARISON SUMMARY  (test 2023-01-01 → 2026-04-25)")
    print(f"  {'Config':<24}  {'K':>3}  {'Final $':>9}  "
          f"{'CAGR':>7}  {'Sharpe':>7}  {'MaxDD':>7}  {'ActvD':>6}")
    print("  " + "─" * 70)

    def _row(rows, K_tgt):
        return next((r for r in rows if int(r['K']) == K_tgt), None)

    for config, label in [
        ('1h_ungated',  '1h  ungated'),
        ('1h_daygated', '1h  day-gated'),
        ('4h_ungated',  '4h  ungated'),
        ('4h_daygated', '4h  day-gated'),
    ]:
        if config not in results:
            continue
        for K_tgt in (1, 5, 14):
            r = _row(results[config], K_tgt)
            if r is None:
                continue
            print(f"  {label:<24}  {K_tgt:>3}  ${r['final']:>8.2f}  "
                  f"{100*r['cagr']:+6.1f}%  "
                  f"{r['sharpe_net']:+6.3f}  "
                  f"{100*r['max_dd']:+6.1f}%  "
                  f"{r['active_days_eq']:5.0f}d")

    if daily_ok:
        d = results.get('daily_ref', {})
        if d:
            print(f"\n  {'Daily v28 K=1  (ref)':<28}  "
                  f"CAGR={100*d['cagr']:+.1f}%  "
                  f"Sharpe={d['sharpe']:+.3f}  "
                  f"MaxDD={100*d['max_dd']:+.1f}%  "
                  f" {d['active_days']}d")
    print("=" * 88)


if __name__ == '__main__':
    main()
