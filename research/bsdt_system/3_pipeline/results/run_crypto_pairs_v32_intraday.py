"""
Crypto BSDT v32 — Intraday (1h / 4h) Simulation
=================================================

Tests whether the v28 production edge survives on sub-daily data.

Data constraint:
  yfinance 1h max lookback ≈ 729 days.
  Intraday test window: ~May 2024 → Apr 2026  (≈ 2 years).
  Daily reference also restricted to same window for fair comparison.

Three configurations:
  [A] 1h UNGATED    — quality-gated trend+pairs+macro, no physics engine
  [B] 4h UNGATED    — same at 4h resolution
  [C] 1h DAY-GATED  — intraday strategies + daily physics gate upsampled
  [D] 4h DAY-GATED  — same at 4h resolution
  [E] DAILY          — v28_full_no_brk restricted to same 2yr window

Window scaling (daily → intraday):
  bars_per_day = 24 (1h)  or  6 (4h)
  trend_N    = 3  × bpd      (3-day momentum equivalent)
  pairs_win  = 20 × bpd
  macro_win  = 30 × bpd
  vol_win    = 20 × bpd      (for quality vol-scaling)
  sharpe_win = 60 × bpd      (for quality sigmoid)
  ann_factor = 252 × bpd

Fee model: 5 bps per active DAY, spread as 5/bpd bps per active bar.
  Keeps total fee burden identical to daily model.
"""
from __future__ import annotations
import os, sys, json, warnings
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
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
from run_crypto_pairs_v28 import build_v28_pnl, V28_KEYS, V28_WCOLS

OUT_DIR_ = Path(OUT_DIR)


# ─── helpers ────────────────────────────────────────────────────────────────

def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


# ═══════════════════════════════════════════════════════════════════════════
#  1.  INTRADAY DATA FETCH
# ═══════════════════════════════════════════════════════════════════════════

def fetch_intraday(period: str = '729d') -> pd.DataFrame:
    """Download 1h OHLCV for ETH, BTC, SOL, BNB via yfinance.

    Returns DataFrame with per-bar log returns and spread features.
    Index is tz-naive UTC-floor DatetimeIndex.
    """
    print(f"  Fetching 1h OHLCV (period={period}) ...")
    tickers = {'ETH-USD': 'eth', 'BTC-USD': 'btc', 'SOL-USD': 'sol', 'BNB-USD': 'bnb'}
    prices = {}
    for tk, col in tickers.items():
        raw = yf.download(tk, period=period, interval='1h',
                          auto_adjust=True, progress=False)
        prices[col] = raw['Close'].squeeze()

    df = pd.DataFrame(prices).dropna()
    # Make index tz-naive
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    for a in ['eth', 'btc', 'sol', 'bnb']:
        df[f'ret_{a}'] = np.log(df[a] / df[a].shift(1))

    df['log_eth'] = np.log(df['eth'])
    df['log_btc'] = np.log(df['btc'])
    df['ret_alt_basket'] = (df['ret_eth'] + df['ret_sol'] + df['ret_bnb']) / 3.0
    df['btc_dom'] = df['ret_btc'] - df['ret_alt_basket']

    df = df.dropna()
    n_days = (df.index[-1] - df.index[0]).days
    print(f"  1h data: {df.index[0]}  →  {df.index[-1]}   "
          f"n={len(df):,} bars  (~{n_days} calendar days)")
    return df


def resample_to_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Resample 1h DataFrame to 4h by aggregating returns (sum) and prices (last)."""
    agg = {}
    for col in df_1h.columns:
        if col.startswith('ret_') or col == 'btc_dom':
            agg[col] = df_1h[col].resample('4h').sum()
        else:
            agg[col] = df_1h[col].resample('4h').last()
    df_4h = pd.DataFrame(agg).dropna()
    # Recompute log columns from prices
    df_4h['log_eth'] = np.log(df_4h['eth'])
    df_4h['log_btc'] = np.log(df_4h['btc'])
    n_days = (df_4h.index[-1] - df_4h.index[0]).days
    print(f"  4h data: {df_4h.index[0]}  →  {df_4h.index[-1]}   "
          f"n={len(df_4h):,} bars  (~{n_days} calendar days)")
    return df_4h


# ═══════════════════════════════════════════════════════════════════════════
#  2.  INTRADAY STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════

def compute_intraday_strategies(df: pd.DataFrame, bpd: int,
                                 verbose: bool = True) -> dict:
    """
    Compute trend / pairs / macro at intraday resolution.

    bpd: bars per day — 24 (1h), 6 (4h).

    Strategy definitions (all scaled to daily equivalents):
      trend   : sign of 3-day rolling return on ETH       → long/short ETH
      pairs   : -z_score of log(ETH/BTC) with 20d window  → spread mean-reversion
      macro   : BTC dominance 30d MA sign                 → BTC momentum vs ETH
      breakout: zeroed (not used in production)
    """
    n = bpd

    # ── trend: 3-day equivalent momentum ──────────────────────────────────
    trend_N = 3 * n
    ret_N = df['ret_eth'].rolling(trend_N, min_periods=n).sum()
    pos_trend = np.sign(ret_N.shift(1))
    pnl_trend = pos_trend * df['ret_eth']

    # ── pairs: ETH vs BTC log-spread z-score mean-reversion ───────────────
    pairs_win = 20 * n
    spread = df['log_eth'] - df['log_btc']
    mu  = spread.rolling(pairs_win, min_periods=n * 4).mean()
    sd  = spread.rolling(pairs_win, min_periods=n * 4).std().clip(lower=1e-9)
    z   = (spread - mu) / sd
    pos_pairs = -np.sign(z.shift(1))          # mean-revert: short spread → long ETH when z<0
    spread_ret = df['ret_eth'] - df['ret_btc'] # ETH minus BTC spread return
    pnl_pairs = pos_pairs * spread_ret

    # ── macro: BTC dominance trend → long BTC / short ETH ─────────────────
    macro_win = 30 * n
    dom_ma = df['btc_dom'].rolling(macro_win, min_periods=n * 4).mean()
    pos_macro = np.sign(dom_ma.shift(1))
    pnl_macro_btc = pos_macro * df['ret_btc']           # long BTC when dominant
    pnl_macro_eth = -pos_macro * df['ret_eth']          # short ETH when BTC dominant
    pnl_macro = (pnl_macro_btc + pnl_macro_eth) / 2.0

    strats = {
        'trend':    pnl_trend.fillna(0.0),
        'pairs':    pnl_pairs.fillna(0.0),
        'breakout': pd.Series(0.0, index=df.index),
        'macro':    pnl_macro.fillna(0.0),
    }

    if verbose:
        ann = 252.0 * bpd
        for k, p in strats.items():
            if k == 'breakout':
                continue
            act  = int((p.abs() > 1e-9).sum())
            sh   = float(p.mean() / p.std() * np.sqrt(ann)) if p.std() > 0 else 0.0
            yrs  = len(p) / ann
            cagr = float((1 + p).prod() ** (1 / max(yrs, 1e-9)) - 1)
            print(f"    {k:<10}  Sharpe={sh:+.3f}  CAGR={100*cagr:+.1f}%  "
                  f"Active={act:,}/{len(p):,} bars")

    return strats


# ═══════════════════════════════════════════════════════════════════════════
#  3.  QUALITY WEIGHTS (scaled for intraday)
# ═══════════════════════════════════════════════════════════════════════════

def compute_intraday_quality_weights(strats: dict, bpd: int,
                                      vol_win_d: int = 20,
                                      sharpe_win_d: int = 60,
                                      sharpe_k: float = 2.0,
                                      scale_cap: float = 5.0) -> pd.DataFrame:
    """
    Build per-bar quality weight for each strategy.

    vol_win_d / sharpe_win_d are in DAILY units; scaled by bpd internally.
    target_vol is per-bar vol target = 0.01 / sqrt(bpd)  (daily 1% → intraday).

    Returns DataFrame[T, 4] with columns matching V28_KEYS (lagged 1 bar).
    """
    vol_win    = vol_win_d    * bpd
    sharpe_win = sharpe_win_d * bpd
    target_vol = 0.01 / np.sqrt(float(bpd))   # daily 1% target vol → per-bar
    ann        = 252.0 * bpd

    out = {}
    for k in V28_KEYS:
        p = strats[k]
        if k == 'breakout':
            out[k] = pd.Series(0.0, index=p.index)
            continue
        rv     = p.rolling(vol_win, min_periods=bpd * 5).std().clip(lower=1e-9)
        rm     = p.rolling(sharpe_win, min_periods=bpd * 10).mean()
        rs     = p.rolling(sharpe_win, min_periods=bpd * 10).std().clip(lower=1e-9)
        rsharpe = (rm / rs) * np.sqrt(ann)
        q      = _sigmoid(rsharpe.fillna(0.0) * sharpe_k)
        scale  = (target_vol / rv).clip(upper=scale_cap)
        out[k] = (q * scale).shift(1).fillna(0.0)

    return pd.DataFrame(out)


# ═══════════════════════════════════════════════════════════════════════════
#  4.  DAILY GATE UPSAMPLER
# ═══════════════════════════════════════════════════════════════════════════

def _upsample_daily_to_intraday(W_daily_normalized: pd.DataFrame,
                                  df_intraday: pd.DataFrame) -> pd.DataFrame:
    """
    Low-level helper: map a daily DataFrame (index = normalized dates)
    to intraday resolution by repeating each date's row for every intraday
    bar that falls on that calendar date.  Missing dates → 0.0.
    """
    intra_dates = pd.to_datetime(df_intraday.index).normalize()
    result = pd.DataFrame(index=df_intraday.index,
                          columns=W_daily_normalized.columns, dtype=float)
    for col in W_daily_normalized.columns:
        d = W_daily_normalized[col].to_dict()
        result[col] = [d.get(dt, 0.0) for dt in intra_dates]
    return result.fillna(0.0)


def build_daygated_pnl_intraday(strats: dict, W_daily: pd.DataFrame,
                                  Q: pd.DataFrame,
                                  df_intraday: pd.DataFrame) -> pd.Series:
    """
    Assemble intraday portfolio PnL using the DAILY engine gate **without**
    look-ahead bias.

    Correct execution semantics
    ─────────────────────────────────────────────────────────────────────────
    Daily engine computes gate at END of day D  →  trade ALL bars of day D+1.

    Implementation:
      1. Shift W_daily by 1 trading day: W1[D] = W_engine[D-1]
      2. Upsample W1 to intraday: every bar on day D  gets W1[D] = W_engine[D-1]
      3. Q is already 1-bar lagged (shift(1) inside compute_intraday_quality_weights)
      4. eff[T] = W_intraday[T] * Q[T]  —  NO further shift here
      5. Renormalize row-wise and weight strategies

    This means bar T on day D uses:
      gate = W_engine[D-1]         (end-of-yesterday gate  ✓)
      quality = Q[T]               (end-of-previous-bar quality  ✓)
    No look-ahead at either the daily or the intraday level.
    """
    # Step 1: shift gate forward by 1 trading day
    W_shifted = W_daily.shift(1).fillna(0.0)
    W_shifted.index = pd.to_datetime(W_shifted.index).normalize()

    # Step 2: upsample to intraday
    W_intra = _upsample_daily_to_intraday(W_shifted, df_intraday)

    # Step 3+4: weighted combination  (Q already shifted in caller)
    eff = pd.DataFrame(0.0, index=df_intraday.index, columns=V28_KEYS)
    for c, k in zip(V28_WCOLS, V28_KEYS):
        eff[k] = W_intra[c] * Q[k]

    # Renormalize rows (same as build_v28_pnl's renorm=True)
    row_sum = eff.sum(axis=1).replace(0.0, np.nan)
    eff = eff.div(row_sum, axis=0).fillna(0.0)

    pnl = pd.Series(0.0, index=df_intraday.index)
    for k in V28_KEYS:
        pnl = pnl + eff[k] * strats[k]
    return pnl


# ═══════════════════════════════════════════════════════════════════════════
#  5.  INTRADAY EQUITY CURVE
# ═══════════════════════════════════════════════════════════════════════════

def equity_intraday(pnl_gross: pd.Series, K: float, bpd: int,
                    *, init: float = 100.0, tcost_bps: float = 5.0) -> dict:
    """
    Simulate equity curve at intraday resolution.

    Fee model: 5 bps per ACTIVE DAY (consistent with daily model).
    Per-bar fee = (tcost_bps / bpd) × 1e-4  when bar has non-zero PnL.
    This ensures the same dollar cost as daily (K=1 active day → 5 bps total).

    Sharpe annualized by sqrt(252 × bpd).
    CAGR based on full calendar duration of the series.
    """
    p     = pnl_gross.fillna(0.0).astype(float) * K
    ann   = 252.0 * bpd
    fee   = (tcost_bps / 1e4 / bpd) * (pnl_gross.fillna(0.0).abs() > 0).astype(float)
    r_net = p - fee
    eq    = init * (1.0 + r_net).cumprod()
    peak  = eq.cummax()
    dd    = (eq - peak) / peak

    # Calendar-based CAGR
    cal_days = (pnl_gross.index[-1] - pnl_gross.index[0]).total_seconds() / 86400.0
    yrs      = cal_days / 365.0

    final = float(eq.iloc[-1])
    # Guard against negative equity (extreme leverage) before power
    cagr  = max(final, 1e-6) / init
    cagr  = float(cagr ** (1.0 / max(yrs, 1e-9)) - 1.0)
    sh    = float(r_net.mean() / r_net.std() * np.sqrt(ann)) if r_net.std() > 0 else 0.0
    act_d = float((r_net.abs() > 1e-9).sum()) / bpd  # equivalent active days

    return {
        'K': float(K), 'final': final, 'pnl_dollar': final - init,
        'sharpe_net': sh, 'cagr': float(cagr), 'max_dd': float(dd.min()),
        'active_days_eq': act_d,
    }


def sweep_K(pnl_gross: pd.Series, bpd: int, tag: str,
            K_vals: list | None = None) -> list:
    """Sweep leverage K, print summary rows, return list of result dicts."""
    if K_vals is None:
        K_vals = list(range(1, 31))
    show_at = {1, 2, 5, 10, 14, 20, 25, 29, 30}

    rows = []
    for K in K_vals:
        m = equity_intraday(pnl_gross, float(K), bpd)
        rows.append(m)

    print(f"\n  {'K':>3}  {'Final $':>9}  {'CAGR':>7}  {'Sharpe':>7}  {'MaxDD':>7}")
    for r in rows:
        if r['K'] in show_at:
            print(f"  {int(r['K']):>3}  ${r['final']:>8.2f}  "
                  f"{100*r['cagr']:+6.1f}%  "
                  f"{r['sharpe_net']:+6.3f}  "
                  f"{100*r['max_dd']:+6.1f}%")

    df_rows = pd.DataFrame(rows)
    print(f"\n  Optimal K under DD limits [{tag}]:")
    for label, lim in [('DD<10%', 0.10), ('DD<20%', 0.20),
                        ('DD<30%', 0.30), ('DD<40%', 0.40)]:
        sub = df_rows[df_rows['max_dd'] > -lim]
        if len(sub) == 0:
            print(f"    {label}: no K satisfies constraint")
            continue
        best = sub.sort_values('sharpe_net', ascending=False).iloc[0]
        print(f"    {label}: K={int(best['K'])}  "
              f"${best['final']:.2f}  "
              f"CAGR={100*best['cagr']:+.1f}%  "
              f"Sharpe={best['sharpe_net']:+.3f}")

    return rows


# ═══════════════════════════════════════════════════════════════════════════
#  6.  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print("=" * 88)
    print("  CRYPTO BSDT v32 — Intraday (1h / 4h) Simulation")
    print("  Quality-gated trend/pairs/macro  |  optional daily physics gate")
    print("=" * 88)

    results = {}

    # ────────────────────────────────────────────────────────────────────────
    # PHASE 1 — Fetch intraday data
    # ────────────────────────────────────────────────────────────────────────
    print("\n[1] Fetching intraday OHLCV ...")
    df_1h = fetch_intraday(period='729d')
    df_4h = resample_to_4h(df_1h)

    intra_start = df_1h.index[0]
    results['intra_start'] = str(intra_start.date())
    results['intra_end']   = str(df_1h.index[-1].date())
    results['n_bars_1h']   = len(df_1h)
    results['n_bars_4h']   = len(df_4h)

    # ────────────────────────────────────────────────────────────────────────
    # PHASE 2 — Compute strategies at each resolution
    # ────────────────────────────────────────────────────────────────────────
    print("\n[2] Strategy signals at 1h ...")
    strats_1h = compute_intraday_strategies(df_1h, bpd=24)

    print("\n[3] Strategy signals at 4h ...")
    strats_4h = compute_intraday_strategies(df_4h, bpd=6)

    # ────────────────────────────────────────────────────────────────────────
    # PHASE 3 — Quality weights (no physics gate)
    # ────────────────────────────────────────────────────────────────────────
    print("\n[4] Computing quality weights ...")
    Q_1h = compute_intraday_quality_weights(strats_1h, bpd=24)
    Q_4h = compute_intraday_quality_weights(strats_4h, bpd=6)

    # Uniform state gate (all 1.0) for ungated configs
    W_uniform_1h = pd.DataFrame(1.0, index=df_1h.index, columns=V28_WCOLS)
    W_uniform_4h = pd.DataFrame(1.0, index=df_4h.index, columns=V28_WCOLS)
    lev_1h = pd.Series(1.0, index=df_1h.index)
    lev_4h = pd.Series(1.0, index=df_4h.index)

    pnl_1h_ug = build_v28_pnl(strats_1h, W_uniform_1h, Q_1h, lev_1h, df_1h.index)
    pnl_4h_ug = build_v28_pnl(strats_4h, W_uniform_4h, Q_4h, lev_4h, df_4h.index)

    print(f"  1h ungated gross Sharpe: "
          f"{float(pnl_1h_ug.mean()/pnl_1h_ug.std()*np.sqrt(252*24)):+.4f}")
    print(f"  4h ungated gross Sharpe: "
          f"{float(pnl_4h_ug.mean()/pnl_4h_ug.std()*np.sqrt(252*6)):+.4f}")

    # ────────────────────────────────────────────────────────────────────────
    # PHASE 4 — K sweep: 1h and 4h UNGATED
    # ────────────────────────────────────────────────────────────────────────
    K_grid = [1, 2, 3, 5, 7, 10, 12, 14, 17, 20, 23, 25, 28, 29, 30]

    print("\n" + "─" * 88)
    print("  [A]  1h UNGATED — quality gate only, no physics engine")
    print("─" * 88)
    results['1h_ungated'] = sweep_K(pnl_1h_ug, bpd=24, tag='1h_ungated', K_vals=K_grid)

    print("\n" + "─" * 88)
    print("  [B]  4h UNGATED — quality gate only, no physics engine")
    print("─" * 88)
    results['4h_ungated'] = sweep_K(pnl_4h_ug, bpd=6, tag='4h_ungated', K_vals=K_grid)

    # ────────────────────────────────────────────────────────────────────────
    # PHASE 5 — Daily pipeline for gate signals + reference
    # ────────────────────────────────────────────────────────────────────────
    print("\n[5] Running daily v28 pipeline (for gate signals and daily reference) ...")
    daily_ok = False
    try:
        df_d = fetch_and_prepare()
        df_d = add_cross_market_features(df_d)
        funding = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'],
                                        start='2020-06-01')
        df_d = add_leverage_features(df_d, funding)

        train_mask     = (df_d.index >= TRAIN_START) & (df_d.index <= TRAIN_END)
        train_mask_arr = np.asarray(train_mask, dtype=bool)
        test_mask      = df_d.index >= TEST_START

        strats_d, F_daily, _, _ = build_book(df_d, train_mask, train_mask_arr)
        W_daily = compute_unsigned_weights(F_daily, use_activation=True,
                                           g_lo=G_LO, k_lo=K_LO)
        from run_crypto_pairs_v28 import compute_quality_risk_weights as cqrw
        Q_daily = cqrw(strats_d, vol_win=60, sharpe_win=120, sharpe_k=2.0)
        lev_d   = pd.Series(1.0, index=df_d.index)

        pnl_daily_full = build_v28_pnl(strats_d, W_daily, Q_daily, lev_d, df_d.index)
        pnl_daily_test = pnl_daily_full[test_mask]

        # Restrict to same window as intraday
        intra_start_dt    = pd.Timestamp(intra_start).normalize()
        same_win_mask     = df_d.index >= intra_start_dt
        pnl_daily_samewin = pnl_daily_full[same_win_mask]

        s_full = simulate_from_pnl(pnl_daily_test.fillna(0.0))
        s_win  = simulate_from_pnl(pnl_daily_samewin.fillna(0.0))

        print(f"\n  [E] Daily v28_full_no_brk — full test 2023→{df_d.index[-1].date()}:")
        print(f"      Sharpe={s_full['sharpe']:+.4f}  "
              f"CAGR={100*s_full['cagr']:+.2f}%  "
              f"MaxDD={100*s_full['max_dd']:+.2f}%  "
              f"Active={int(s_full['active_days'])}d")

        print(f"\n  [E'] Daily restricted to intraday window ({intra_start.date()}→now):")
        print(f"      Sharpe={s_win['sharpe']:+.4f}  "
              f"CAGR={100*s_win['cagr']:+.2f}%  "
              f"MaxDD={100*s_win['max_dd']:+.2f}%  "
              f"Active={int(s_win['active_days'])}d")

        results['daily_full'] = {
            'sharpe': float(s_full['sharpe']),
            'cagr':   float(s_full['cagr']),
            'max_dd': float(s_full['max_dd']),
        }
        results['daily_samewin'] = {
            'sharpe': float(s_win['sharpe']),
            'cagr':   float(s_win['cagr']),
            'max_dd': float(s_win['max_dd']),
        }

        # ── Day-gated intraday ────────────────────────────────────────────
        print("\n[6] Upsampling daily gate to 1h and 4h (1-day pre-shift, no look-ahead) ...")
        pnl_1h_gated = build_daygated_pnl_intraday(strats_1h, W_daily, Q_1h, df_1h)
        pnl_4h_gated = build_daygated_pnl_intraday(strats_4h, W_daily, Q_4h, df_4h)

        act_1h_days = (pnl_1h_gated.abs() > 1e-9).sum() / 24
        act_4h_days = (pnl_4h_gated.abs() > 1e-9).sum() / 6
        print(f"  1h day-gated gross Sharpe: "
              f"{float(pnl_1h_gated.mean()/pnl_1h_gated.std()*np.sqrt(252*24)):+.4f}  "
              f"active≈{act_1h_days:.0f}d  (daily active={int(s_win['active_days'])}d expected)")
        print(f"  4h day-gated gross Sharpe: "
              f"{float(pnl_4h_gated.mean()/pnl_4h_gated.std()*np.sqrt(252*6)):+.4f}  "
              f"active≈{act_4h_days:.0f}d")

        print("\n" + "─" * 88)
        print("  [C]  1h DAY-GATED — daily physics gate + intraday quality")
        print("─" * 88)
        results['1h_daygated'] = sweep_K(pnl_1h_gated, bpd=24,
                                          tag='1h_daygated', K_vals=K_grid)

        print("\n" + "─" * 88)
        print("  [D]  4h DAY-GATED — daily physics gate + intraday quality")
        print("─" * 88)
        results['4h_daygated'] = sweep_K(pnl_4h_gated, bpd=6,
                                          tag='4h_daygated', K_vals=K_grid)
        daily_ok = True

    except Exception as exc:
        import traceback
        print(f"\n  [WARNING] Daily pipeline failed: {exc}")
        traceback.print_exc()
        print("  Continuing with ungated configs only.")

    # ────────────────────────────────────────────────────────────────────────
    # PHASE 6 — Save results + print comparison table
    # ────────────────────────────────────────────────────────────────────────
    out_path = OUT_DIR_ / 'crypto_bsdt_v32_intraday.json'
    with open(out_path, 'w') as fh:
        json.dump(results, fh, indent=2, default=float)
    print(f"\n  Saved → {out_path}")

    # ── Comparison summary at K=14 and K=29 ─────────────────────────────
    print("\n" + "=" * 88)
    print("  COMPARISON SUMMARY  (test window: intraday start → Apr 2026)")
    print(f"  {'Config':<22}  {'K':>3}  {'Final $':>9}  {'CAGR':>7}  "
          f"{'Sharpe':>7}  {'MaxDD':>7}")
    print("  " + "─" * 62)

    def _find_K(rows, K_target):
        for r in rows:
            if int(r['K']) == K_target:
                return r
        return None

    for config, label in [
        ('1h_ungated',   '1h  ungated'),
        ('4h_ungated',   '4h  ungated'),
        ('1h_daygated',  '1h  day-gated'),
        ('4h_daygated',  '4h  day-gated'),
    ]:
        if config not in results:
            continue
        for K_tgt in (14, 29):
            r = _find_K(results[config], K_tgt)
            if r is None:
                continue
            print(f"  {label:<22}  {K_tgt:>3}  ${r['final']:>8.2f}  "
                  f"{100*r['cagr']:+6.1f}%  "
                  f"{r['sharpe_net']:+6.3f}  "
                  f"{100*r['max_dd']:+6.1f}%")

    if daily_ok:
        for label2, key2 in [('Daily full (3.3yr)', 'daily_full'),
                              ('Daily same window',  'daily_samewin')]:
            d = results.get(key2)
            if d:
                print(f"  {label2:<26}  Sharpe={d['sharpe']:+.3f}  "
                      f"CAGR={100*d['cagr']:+.1f}%  "
                      f"MaxDD={100*d['max_dd']:+.1f}%")

    print("=" * 88)


if __name__ == '__main__':
    main()
