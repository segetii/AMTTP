"""
Crypto BSDT v34 — FULL COMBINED SYSTEM: All Strategies, All Timeframes
=======================================================================

Combines EVERY profitable strategy identified across v1–v33:

  DAILY strategies (positions from daily signals, held 24h, applied to 1h bars):
    D1  trend_eth_daily   : v28 A_directional position on ETH
    D2  pairs_ethbtc_daily: ETH/BTC z-score mean-reversion (P1 from v28)
    D3  pairs_ethsol_daily: ETH/SOL z-score mean-reversion (P2 from v28)
    D4  macro_btc_daily   : BTC flight-to-safety macro (pos_btc_macro)
    D5  macro_alt_daily   : alt-season macro (pos_alt_macro on ETH)
    → All 5 daily strategies gated by physics engine (geom>0.5 & kp>0.3)
    → 1-day signal lag enforced: signal on day D → positions on day D+1

  INTRADAY 1h strategies (positions computed per bar, held 1 bar):
    H1  trend_eth_1h      : sign(3d ETH cumulative return)
    H2  trend_btc_1h      : sign(3d BTC cumulative return)
    H3  pairs_trend_1h    : sign(3d ETH-BTC spread return)  ←  Sharpe +2.67
    H4  macro_1h          : sign(7d BTC dominance MA)
    → Run ungated (quality gate only); physics gate hurts 1h performance

  CROSS-ASSET 1h strategies (from F3 fragility: BTC and SOL work independently):
    H5  trend_btc_1h_crs  : 3d BTC momentum applied to BTC
    H6  trend_sol_1h_crs  : 3d SOL momentum applied to SOL (when available)

QUALITY GATE:
  Rolling-Sharpe sigmoid × vol-scaling for every strategy (at 1h resolution).
  Lagged 1 bar — no look-ahead.

PHYSICS GATE:
  Daily binary: (geom_score > G_LO) & (kramers_p > K_LO), shifted 1 trading day.
  Applied only to D1-D5.

PORTFOLIO ASSEMBLY:
  quality_eff[s] = Q_quality[s] × gate[s]   (gate=1 for H-series, daily gate for D-series)
  row-normalise → combined PnL

RESULTS:
  Yearly breakdown 2023-2026
  K sweep K=1..30
  Comparison vs daily-only v28 and 1h-only v33
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
    compute_bsdt, compute_gamma_rank, compute_activity_signals,
    compute_state_vector, compute_geom_signals_v18_smooth,
    apply_geom_penalties_v18, compute_leverage_dial,
    compute_rolling_spread_v8, SpreadUDLClassifier,
    compute_manifold_validity, detect_phase,
    route_pair_v7, route_btcalt_macro, setup_a_directional,
    get_daily_pnl, _build_state_panel,
    simulate_from_pnl,
    TRAIN_START, TRAIN_END, TEST_START, OUT_DIR,
    GAMMA_SCORE_WIN,
)
from run_crypto_pairs_v22 import (
    calibrate_frozen_engine, patch_precursor_scale, emit_global_signals,
)
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


# ═══════════════════════════════════════════════════════════════════════════
#  1.  FETCH FULL BINANCE 1h HISTORY
# ═══════════════════════════════════════════════════════════════════════════

def fetch_klines(symbol: str, start: str, end: str, interval: str = '1h') -> pd.Series:
    url   = 'https://api.binance.com/api/v3/klines'
    iv_ms = {'1h': 3_600_000, '4h': 14_400_000}.get(interval, 3_600_000)
    s_ms  = int(pd.Timestamp(start).timestamp() * 1000)
    e_ms  = int(pd.Timestamp(end).timestamp() * 1000)
    recs, cur, fails = [], s_ms, 0
    while cur < e_ms:
        try:
            r = requests.get(url, params={
                'symbol': symbol, 'interval': interval,
                'startTime': cur, 'endTime': e_ms, 'limit': 1000,
            }, timeout=30)
            data = r.json()
            if not isinstance(data, list) or not data:
                break
            recs.extend(data)
            cur = int(data[-1][0]) + iv_ms
            if len(data) < 1000:
                break
            time.sleep(0.04)
            fails = 0
        except Exception as exc:
            fails += 1
            if fails >= 4:
                print(f"  [warn] {symbol} fetch stopped: {exc}")
                break
            time.sleep(1.5)
    if not recs:
        return pd.Series(dtype=float, name=symbol)
    ts   = pd.to_datetime([int(r[0]) for r in recs], unit='ms').tz_localize(None)
    vals = np.array([float(r[4]) for r in recs])
    return pd.Series(vals, index=ts, name=symbol).sort_index().drop_duplicates()


def build_1h_df(start: str = '2021-01-01', end: str = '2026-06-01') -> pd.DataFrame:
    """Fetch 1h OHLCV from Binance: ETH, BTC, SOL (best-effort)."""
    sym_map = [('ETHUSDT','eth'), ('BTCUSDT','btc'), ('SOLUSDT','sol')]
    prices  = {}
    for sym, col in sym_map:
        print(f"  {sym} 1h ...", end=' ', flush=True)
        s = fetch_klines(sym, start, end)
        if len(s):
            print(f"{len(s):,} bars  [{s.index[0].date()} → {s.index[-1].date()}]")
        prices[col] = s

    # Use ETH+BTC always; add SOL if it covers the train period
    base_df = pd.DataFrame({'eth': prices['eth'], 'btc': prices['btc']}).dropna()
    sol     = prices.get('sol', pd.Series(dtype=float))
    has_sol = len(sol) > 0 and sol.index[0] <= pd.Timestamp('2021-06-01')

    if has_sol:
        base_df = pd.concat([base_df, sol.rename('sol')], axis=1).dropna()
        print(f"  SOL included (data from {sol.index[0].date()})")
    else:
        base_df['sol'] = base_df['eth']   # placeholder, will only use if has_sol
        has_sol = False

    for a in ['eth','btc','sol']:
        base_df[f'ret_{a}']  = np.log(base_df[a] / base_df[a].shift(1))
        base_df[f'log_{a}']  = np.log(base_df[a])
    base_df['btc_dom']     = base_df['ret_btc'] - base_df['ret_eth']
    base_df['spread_eb']   = base_df['log_eth'] - base_df['log_btc']   # ETH-BTC log spread
    base_df['spread_ret_eb'] = base_df['ret_eth'] - base_df['ret_btc']
    base_df = base_df.dropna()

    n = (base_df.index[-1] - base_df.index[0]).days
    n_train = int(((base_df.index >= TRAIN_START) & (base_df.index < TEST_START)).sum())
    n_test  = int((base_df.index >= TEST_START).sum())
    print(f"\n  1h DataFrame: {base_df.index[0]}  →  {base_df.index[-1]}   "
          f"n={len(base_df):,} bars  ({n} days)")
    print(f"  Train: {n_train:,}   Test: {n_test:,}   SOL: {has_sol}")
    return base_df, has_sol


# ═══════════════════════════════════════════════════════════════════════════
#  2.  DAILY PIPELINE → POSITIONS + GATE
# ═══════════════════════════════════════════════════════════════════════════

def build_daily_positions(df_d: pd.DataFrame,
                           train_mask_d: pd.Series,
                           train_mask_arr: np.ndarray) -> tuple:
    """
    Full v28 daily pipeline.
    Returns:
      pos_dict  : {name: daily position Series}
      F_daily   : global signal DataFrame
      gate_mask : daily boolean Series (geom & kp gate, shift(1) already applied)
    """
    feats_strat = ['ret_eth_z','ret_btc_z','ret_sol_z','ret_bnb_z',
                   'vol_eth_z','vol_btc_z','btc_dom_z','cross_disp_z']
    feats_ext   = feats_strat + ['ret_spx_z','dvix_z','ret_dxy_z']

    omega_strat, mfls_eth, gamma_eth = compute_bsdt(df_d, feats_strat, window=60)
    omega_ext,   _,        _         = compute_bsdt(df_d, feats_ext,   window=60)
    _, A_rank, dA_fast, dA_rank      = compute_activity_signals(mfls_eth, gamma_eth)
    gamma_rank  = compute_gamma_rank(omega_ext, min_periods=60)
    ret7  = df_d['ret_eth'].rolling(7).sum()
    ret3  = df_d['ret_eth'].rolling(3).sum()
    phase = detect_phase(omega_strat, ret7, ret3, df_d['btc_dom_z'])

    sys.path.insert(0, r"C:\amttp")
    from crypto_eigen_direction_patch import compute_crypto_eigen_direction, setup_a_directional_eigen
    
    # ── M2 Eigenvector Loading (Geometric Direction) ──
    # Computes dominant instability mode loading on eth returns (ret_idx=0 since 'ret_eth_z' is index 0)
    evec_loading = compute_crypto_eigen_direction(df_d, feats_strat, window=60, ret_idx=0)

    # A_directional (D1) using true structural direction
    pos_trend = setup_a_directional_eigen(df_d, omega_strat, mfls_eth, gamma_eth, phase, evec_loading)

    # Two pairs (P1 ETH/BTC, P2 ETH/SOL)
    pair_pos_list = []
    for key, col_a, col_b, ret_a, ret_b in [
        ('P1_ETH_BTC','log_eth','log_btc','ret_eth','ret_btc'),
        ('P2_ETH_SOL','log_eth','log_sol','ret_eth','ret_sol'),
    ]:
        sd = compute_rolling_spread_v8(
            df_d[col_a], df_d[col_b], df_d[ret_a], df_d[ret_b],
            train_mask=train_mask_d, beta_window=252)
        clf = SpreadUDLClassifier(window=20, n_ref_dirs=100).fit(
            sd['spread'][train_mask_d].dropna())
        udl_s, _, _ = clf.classify_series(sd['spread'])
        sd['udl_state'] = udl_s
        mval, _ = compute_manifold_validity(sd['z'], sd['sret'])
        sd['manifold_valid'] = mval
        pos = route_pair_v7(omega_strat, A_rank, sd['z'], sd['udl_state'],
                             sd['poa'], sd['manifold_valid'])
        pair_pos_list.append((key, pos, sd['sret']))

    # Macro (pos_btc, pos_alt)
    pos_btc_macro, pos_alt_macro = route_btcalt_macro(df_d, omega_strat, A_rank, dA_rank)

    # Physics engine
    X_panel = _build_state_panel(df_d)
    M, net, geom_e, lyap, info, ews, e_star, sigma_n = calibrate_frozen_engine(
        X_panel, train_mask_arr)
    patch_precursor_scale(ews, M, X_panel[train_mask_arr])
    F = emit_global_signals(df_d, X_panel, M, net, geom_e, lyap, ews, sigma_n)

    # Daily gate (shift 1 day already): active[D-1] applied to day D
    geom_n = F['geom_score'].fillna(0.0)
    kp     = F['kramers_p'].fillna(0.0)
    gate   = ((geom_n > G_LO) & (kp > K_LO)).astype(float).shift(1).fillna(0.0).astype(bool)

    pos_dict = {
        'D1_trend_eth':   pos_trend,
        'D2_pairs_eb':    pair_pos_list[0][1],   # ETH/BTC spread pos
        'D3_pairs_es':    pair_pos_list[1][1],   # ETH/SOL spread pos
        'D4_macro_btc':   pos_btc_macro,
        'D5_macro_alt':   pos_alt_macro,
    }
    spread_ret = {
        'D2_pairs_eb': pair_pos_list[0][2],   # sret for ETH/BTC
        'D3_pairs_es': pair_pos_list[1][2],   # sret for ETH/SOL
    }

    return pos_dict, spread_ret, F, gate


# ═══════════════════════════════════════════════════════════════════════════
#  3.  UPSAMPLE DAILY POSITIONS → 1h PnL SERIES
# ═══════════════════════════════════════════════════════════════════════════

def upsample_daily_to_1h_pnl(pos_daily: pd.Series,
                               ret_1h: pd.Series,
                               gate_daily: pd.Series) -> pd.Series:
    """
    Strategy position computed daily at EOD, held through all bars of next day.
    Gate is ALSO daily (already shifted 1 day in build_daily_positions).

    pos[D] × gate[D]  →  applied to ret_1h[bars on day D]

    That means: for each bar t on day D, pnl_bar[t] = pos[D-1] × gate[D-1] × ret[t]
    (The pos and gate are already 1-day lagged as computed, so direct mapping to D is correct.)
    """
    # Normalize daily index to date
    idx = pd.to_datetime(pos_daily.index).normalize()
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    pos_normed  = pd.Series(pos_daily.values, index=idx)
    gate_normed = pd.Series(gate_daily.astype(float).values, index=idx)

    # For each 1h bar, look up its calendar date
    intra_dates = pd.to_datetime(ret_1h.index).normalize()
    pos_bar  = pd.Series([pos_normed.get(d, 0.0) for d in intra_dates],
                          index=ret_1h.index, dtype=float)
    gate_bar = pd.Series([gate_normed.get(d, 0.0) for d in intra_dates],
                          index=ret_1h.index, dtype=float)

    pnl = pos_bar * gate_bar * ret_1h.reindex(ret_1h.index).fillna(0.0)
    return pnl.fillna(0.0)


# ═══════════════════════════════════════════════════════════════════════════
#  4.  1h INTRADAY STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════

def compute_1h_strategies(df: pd.DataFrame, has_sol: bool) -> dict:
    """
    H1-H6 intraday strategies. All signals shifted 1 bar.
    Returns dict of PnL series.
    """
    BPD = 24
    N3  = 3 * BPD   # 3-day momentum
    N7  = 7 * BPD   # 7-day macro

    # H1 trend ETH
    mH1   = df['ret_eth'].rolling(N3, min_periods=BPD).sum()
    pnl_H1 = np.sign(mH1.shift(1)) * df['ret_eth']

    # H2 trend BTC
    mH2   = df['ret_btc'].rolling(N3, min_periods=BPD).sum()
    pnl_H2 = np.sign(mH2.shift(1)) * df['ret_btc']

    # H3 ETH/BTC spread TREND-FOLLOWING (winner from v33)
    mH3   = df['spread_ret_eb'].rolling(N3, min_periods=BPD).sum()
    pnl_H3 = np.sign(mH3.shift(1)) * df['spread_ret_eb']

    # H4 macro BTC dominance
    mH4  = df['btc_dom'].rolling(N7, min_periods=2 * BPD).mean()
    pos_macro = np.sign(mH4.shift(1))
    pnl_H4 = (pos_macro * df['ret_btc'] + (-pos_macro) * df['ret_eth']) / 2.0

    strats = {
        'H1_trend_eth': pnl_H1.fillna(0.0),
        'H2_trend_btc': pnl_H2.fillna(0.0),
        'H3_pairs_trd': pnl_H3.fillna(0.0),
        'H4_macro':     pnl_H4.fillna(0.0),
    }

    # H5 SOL trend (only if we have real SOL data)
    if has_sol and 'ret_sol' in df.columns:
        mH5   = df['ret_sol'].rolling(N3, min_periods=BPD).sum()
        strats['H5_trend_sol'] = (np.sign(mH5.shift(1)) * df['ret_sol']).fillna(0.0)

    return strats


# ═══════════════════════════════════════════════════════════════════════════
#  5.  QUALITY WEIGHTS
# ═══════════════════════════════════════════════════════════════════════════

def compute_quality(strats: dict, bpd: int = 24,
                     vol_d: int = 60, sh_d: int = 120,
                     sh_k: float = 2.0, cap: float = 5.0) -> pd.DataFrame:
    """Per-bar quality × vol-scale, lagged 1 bar."""
    vol_w  = vol_d * bpd
    sh_w   = sh_d  * bpd
    t_vol  = 0.01 / np.sqrt(float(bpd))
    ann    = 252.0 * bpd
    out    = {}
    for k, p in strats.items():
        if p.abs().max() < 1e-12:
            out[k] = pd.Series(0.0, index=p.index)
            continue
        rv      = p.rolling(vol_w, min_periods=bpd * 5).std().clip(lower=1e-9)
        rm      = p.rolling(sh_w,  min_periods=bpd * 10).mean()
        rs      = p.rolling(sh_w,  min_periods=bpd * 10).std().clip(lower=1e-9)
        rsharpe = (rm / rs) * np.sqrt(ann)
        q       = _sigmoid(rsharpe.fillna(0.0) * sh_k)
        scale   = (t_vol / rv).clip(upper=cap)
        out[k]  = (q * scale).shift(1).fillna(0.0)
    return pd.DataFrame(out)


# ═══════════════════════════════════════════════════════════════════════════
#  6.  PORTFOLIO ASSEMBLY
# ═══════════════════════════════════════════════════════════════════════════

def assemble_combined(all_pnls: dict, Q: pd.DataFrame) -> pd.Series:
    """
    Row-normalize quality weights across all strategies, compute combined PnL.
    Strategies not in Q get zero weight.
    """
    cols = list(all_pnls.keys())
    eff  = pd.DataFrame({k: Q[k] for k in cols if k in Q.columns},
                         index=Q.index)
    missing = [k for k in cols if k not in Q.columns]
    for k in missing:
        eff[k] = 0.0

    row_sum = eff.sum(axis=1).replace(0.0, np.nan)
    eff     = eff.div(row_sum, axis=0).fillna(0.0)

    pnl = pd.Series(0.0, index=Q.index)
    for k in cols:
        p = all_pnls[k].reindex(Q.index, fill_value=0.0)
        pnl = pnl + eff[k] * p
    return pnl


# ═══════════════════════════════════════════════════════════════════════════
#  7.  EQUITY CURVE + K SWEEP
# ═══════════════════════════════════════════════════════════════════════════

def equity_curve(pnl: pd.Series, K: float, bpd: int = 24, *,
                  init: float = 100.0, tcost_bps: float = 5.0) -> dict:
    p     = pnl.fillna(0.0) * float(K)
    fee   = (tcost_bps / 1e4 / bpd) * (pnl.fillna(0.0).abs() > 1e-12).astype(float)
    r_net = p - fee
    eq    = init * (1.0 + r_net).cumprod()
    peak  = eq.cummax()
    dd    = (eq - peak) / peak
    cal_d = max((pnl.index[-1] - pnl.index[0]).total_seconds() / 86400.0, 1.0)
    yrs   = cal_d / 365.0
    final = float(eq.iloc[-1])
    cagr  = float(max(final, 1e-6) / init) ** (1.0 / yrs) - 1.0
    sh    = float(r_net.mean() / r_net.std() * np.sqrt(252.0 * bpd)) if r_net.std() > 0 else 0.0
    act_d = float((r_net.abs() > 1e-12).sum()) / bpd
    return {'K': float(K), 'final': final, 'pnl_dollar': final - init,
            'sharpe_net': sh, 'cagr': float(cagr),
            'max_dd': float(dd.min()), 'active_days_eq': float(act_d)}


def sweep_K(pnl: pd.Series, bpd: int, tag: str,
            K_vals: list | None = None) -> list:
    if K_vals is None:
        K_vals = [1, 2, 3, 4, 5, 7, 10, 12, 14, 17, 20, 23, 25, 28, 29, 30]
    show = {1, 5, 10, 14, 20, 25, 29}
    rows = [equity_curve(pnl, K, bpd) for K in K_vals]
    df_r = pd.DataFrame(rows)

    print(f"\n  {'K':>3}  {'Final $':>9}  {'CAGR':>7}  {'Sharpe':>7}  {'MaxDD':>7}")
    for r in rows:
        if r['K'] in show:
            print(f"  {int(r['K']):>3}  ${r['final']:>8.2f}  "
                  f"{100*r['cagr']:+6.1f}%  "
                  f"{r['sharpe_net']:+6.3f}  "
                  f"{100*r['max_dd']:+6.1f}%")

    print(f"\n  Optimal K [{tag}]:")
    for lbl, lim in [('DD<10%',0.10),('DD<20%',0.20),
                      ('DD<30%',0.30),('DD<40%',0.40)]:
        sub = df_r[df_r['max_dd'] > -lim]
        if sub.empty:
            print(f"    {lbl}: none")
            continue
        best = sub.sort_values('sharpe_net', ascending=False).iloc[0]
        print(f"    {lbl}: K={int(best['K'])}  ${best['final']:.2f}  "
              f"CAGR={100*best['cagr']:+.1f}%  Sharpe={best['sharpe_net']:+.3f}")
    return rows


def yearly_breakdown(pnl: pd.Series, K: float, bpd: int = 24,
                      tcost_bps: float = 5.0) -> None:
    """Print year-by-year P&L at given K."""
    r_net = pnl.fillna(0.0) * K - (tcost_bps / 1e4 / bpd) * (pnl.fillna(0.0).abs() > 1e-12)
    print(f"\n  Year-by-year at K={K}:")
    for yr in [2023, 2024, 2025, 2026]:
        mask = (pnl.index.year == yr)
        if mask.sum() < 10:
            continue
        r_yr   = r_net[mask]
        eq_yr  = (1 + r_yr).prod() - 1.0
        dd_yr  = float(((1 + r_yr).cumprod() / (1 + r_yr).cumprod().cummax() - 1).min())
        act_yr = int((r_yr.abs() > 1e-12).sum()) / bpd
        sh_yr  = float(r_yr.mean() / r_yr.std() * np.sqrt(252.0 * bpd)) if r_yr.std() > 0 else 0.0
        print(f"    {yr}:  return={100*eq_yr:+6.1f}%  MaxDD={100*dd_yr:+5.1f}%  "
              f"Sharpe={sh_yr:+.2f}  active≈{act_yr:.0f}d")


# ═══════════════════════════════════════════════════════════════════════════
#  8.  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print("=" * 92)
    print("  CRYPTO BSDT v34 — FULL COMBINED SYSTEM")
    print("  D1-D5 daily (physics-gated)  +  H1-H5 hourly (quality-gated)")
    print("=" * 92)

    results = {}

    # ────────────────────────────────────────────────────────── DATA ──
    print("\n[1] Fetching full Binance 1h history (ETH, BTC, SOL) ...")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-06-01')

    test_mask_1h  = df_1h.index >= TEST_START
    train_mask_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)

    print(f"\n  Test bars: {test_mask_1h.sum():,}   "
          f"Train bars: {train_mask_1h.sum():,}")

    # ─────────────────────────────────────────── 1h STRATEGIES (H1-H5) ──
    print("\n[2] Computing 1h intraday strategies ...")
    h_strats = compute_1h_strategies(df_1h, has_sol)

    ann_1h = 252.0 * 24
    print(f"\n  Per-strategy standalone [test 2023→2026]:")
    print(f"  {'name':<18}  {'Sharpe':>8}  {'CAGR':>8}  {'MaxDD':>8}")
    for k, p in h_strats.items():
        pt = p[test_mask_1h].fillna(0.0)
        if pt.std() < 1e-12:
            continue
        sh   = float(pt.mean() / pt.std() * np.sqrt(ann_1h))
        yrs  = (pt.index[-1] - pt.index[0]).days / 365.0
        cagr = float((1 + pt).prod() ** (1 / max(yrs, 1e-9)) - 1)
        eq   = (1 + pt).cumprod()
        mdd  = float((eq / eq.cummax() - 1).min())
        print(f"  {k:<18}  {sh:+8.3f}  {100*cagr:+7.1f}%  {100*mdd:+7.1f}%")

    # ───────────────────────────────────────── DAILY PIPELINE (D1-D5) ──
    print("\n[3] Running daily v28 pipeline (positions + physics gate) ...")
    df_d = fetch_and_prepare()
    df_d = add_cross_market_features(df_d)
    funding = fetch_binance_funding(symbols=['ETHUSDT','BTCUSDT'], start='2020-06-01')
    df_d = add_leverage_features(df_d, funding)

    train_mask_d   = (df_d.index >= TRAIN_START) & (df_d.index <= TRAIN_END)
    train_mask_arr = np.asarray(train_mask_d, dtype=bool)
    test_mask_d    = df_d.index >= TEST_START

    print("\n  Building positions and gate ...")
    pos_dict, spread_ret_dict, F_daily, gate_daily = build_daily_positions(
        df_d, train_mask_d, train_mask_arr)

    n_gate = int(gate_daily[test_mask_d].sum())
    print(f"  Gate active: {n_gate} days in test period "
          f"({100*n_gate/int(test_mask_d.sum()):.1f}% of test days)")

    # Build daily reference pnl (v28 production)
    from run_crypto_pairs_v30_perp_realism import build_book
    strats_d_v28, _, _, _ = build_book(df_d, train_mask_d, train_mask_arr)
    W_d   = compute_unsigned_weights(F_daily, use_activation=True, g_lo=G_LO, k_lo=K_LO)
    Q_d   = daily_cqrw(strats_d_v28, vol_win=60, sharpe_win=120, sharpe_k=2.0)
    lev_d = pd.Series(1.0, index=df_d.index)
    pnl_v28_daily = build_v28_pnl(strats_d_v28, W_d, Q_d, lev_d, df_d.index)
    s_ref = simulate_from_pnl(pnl_v28_daily[test_mask_d].fillna(0.0))
    print(f"\n  [E] Daily reference v28_full_no_brk:")
    print(f"      Sharpe={s_ref['sharpe']:+.4f}  "
          f"CAGR={100*s_ref['cagr']:+.2f}%  "
          f"MaxDD={100*s_ref['max_dd']:+.2f}%  "
          f"Active={int(s_ref['active_days'])}d")
    results['daily_v28_ref'] = {
        'sharpe': float(s_ref['sharpe']), 'cagr': float(s_ref['cagr']),
        'max_dd': float(s_ref['max_dd']), 'active': int(s_ref['active_days']),
    }

    # ──────────────────────────────── UPSAMPLE DAILY → 1h PnL SERIES ──
    print("\n[4] Upsampling daily positions to 1h PnL series ...")

    # Map instruments to 1h return series
    instr_map = {
        'D1_trend_eth': df_1h['ret_eth'],
        'D2_pairs_eb':  df_1h['spread_ret_eb'],
        'D3_pairs_es':  (df_1h['ret_eth'] - df_1h.get('ret_sol', df_1h['ret_eth'])),
        'D4_macro_btc': df_1h['ret_btc'],
        'D5_macro_alt': df_1h['ret_eth'],
    }

    d_strats_1h = {}
    for name, pos in pos_dict.items():
        ret_1h_s = instr_map.get(name, df_1h['ret_eth'])
        p = upsample_daily_to_1h_pnl(pos, ret_1h_s, gate_daily)
        d_strats_1h[name] = p

    # Show standalone for D-series (test period only)
    print(f"\n  Per-strategy standalone at 1h [D-series, test 2023→2026]:")
    print(f"  {'name':<18}  {'Sharpe':>8}  {'CAGR':>8}  {'MaxDD':>8}  {'Actv':>6}")
    for k, p in d_strats_1h.items():
        pt = p[test_mask_1h].fillna(0.0)
        if pt.std() < 1e-12:
            continue
        sh   = float(pt.mean() / pt.std() * np.sqrt(ann_1h))
        yrs  = (pt.index[-1] - pt.index[0]).days / 365.0
        cagr = float((1 + pt).prod() ** (1 / max(yrs, 1e-9)) - 1)
        eq   = (1 + pt).cumprod()
        mdd  = float((eq / eq.cummax() - 1).min())
        act  = float((pt.abs() > 1e-12).sum()) / 24
        print(f"  {k:<18}  {sh:+8.3f}  {100*cagr:+7.1f}%  "
              f"{100*mdd:+7.1f}%  {act:5.0f}d")

    # ──────────────────────────────────────── COMBINE ALL STRATEGIES ──
    print("\n[5] Building combined portfolio ...")

    all_pnls = {**d_strats_1h, **h_strats}
    Q_all    = compute_quality(all_pnls, bpd=24)

    pnl_combined = assemble_combined(all_pnls, Q_all)
    pnl_test     = pnl_combined[test_mask_1h]

    sh_gross = float(pnl_test.mean() / pnl_test.std() * np.sqrt(ann_1h)) if pnl_test.std() > 0 else 0.0
    act_d    = float((pnl_test.abs() > 1e-12).sum()) / 24
    print(f"\n  Combined gross Sharpe (test): {sh_gross:+.4f}   Active≈{act_d:.0f}d")
    results['combined_gross_sharpe'] = float(sh_gross)

    # ──────────────────────────────────── BASELINES: H-only, D-only ──
    print("\n  [H-only] 1h strategies ungated baseline ...")
    Q_h   = compute_quality(h_strats, bpd=24)
    row_h = {k: Q_h[k] for k in h_strats if k in Q_h.columns}
    pnl_h = assemble_combined(h_strats, pd.DataFrame(row_h))
    pnl_h_test = pnl_h[test_mask_1h]
    sh_h = float(pnl_h_test.mean() / pnl_h_test.std() * np.sqrt(ann_1h)) if pnl_h_test.std() > 0 else 0.0
    print(f"  H-only gross Sharpe: {sh_h:+.4f}")

    print("\n" + "─" * 92)
    print("  [CONFIG A]  H-series only (1h, quality-gated, ungated)")
    print("─" * 92)
    results['H_only'] = sweep_K(pnl_h_test, bpd=24, tag='H_only')
    yearly_breakdown(pnl_h_test, K=2, bpd=24)

    print("\n" + "─" * 92)
    print("  [CONFIG B]  FULL COMBINED — D1-D5 (daily gated) + H1-H5 (quality-gated)")
    print("─" * 92)
    results['combined'] = sweep_K(pnl_test, bpd=24, tag='combined')
    yearly_breakdown(pnl_test, K=2, bpd=24)

    # ─────────────────────────────────────────────── KELLY ESTIMATES ──
    print(f"\n[6] Kelly estimates:")
    for label, p in [('H-only',   pnl_h_test),
                      ('Combined', pnl_test)]:
        m  = float(p.mean())
        s  = float(p.std())
        if s < 1e-12:
            continue
        full_k = float(m / (s ** 2)) if s > 0 else 0.0
        half_k = full_k / 2.0
        print(f"  {label:<12}  mean={m*1e4:+.2f} bps/bar  "
              f"std={s*1e4:.2f} bps/bar  "
              f"full_K={full_k:.0f}  half_K={half_k:.0f}")

    # Best K at DD<20% for combined
    df_r = pd.DataFrame(results.get('combined', []))
    if not df_r.empty:
        sub = df_r[df_r['max_dd'] > -0.20]
        if not sub.empty:
            best = sub.sort_values('sharpe_net', ascending=False).iloc[0]
            print(f"\n  ★ COMBINED best at DD<20%: K={int(best['K'])}  "
                  f"${best['final']:.2f}  CAGR={100*best['cagr']:+.1f}%  "
                  f"Sharpe={best['sharpe_net']:+.3f}")
            results['best_combined_dd20'] = {
                'K': int(best['K']), 'final': float(best['final']),
                'cagr': float(best['cagr']), 'sharpe': float(best['sharpe_net']),
            }

    # ─────────────────────────────────────────────────── SAVE + TABLE ──
    out = OUT_DIR_ / 'crypto_bsdt_v34_full_combined.json'
    with open(out, 'w') as fh:
        json.dump(results, fh, indent=2, default=float)
    print(f"\n  Saved → {out}")

    print("\n" + "=" * 92)
    print("  MASTER COMPARISON TABLE")
    print(f"  {'Config':<30}  {'K':>3}  {'$100→':>9}  {'CAGR':>7}  "
          f"{'Sharpe':>7}  {'MaxDD':>7}")
    print("  " + "─" * 68)

    def _at(rows, K_tgt):
        return next((r for r in rows if int(r['K']) == K_tgt), None)

    # H-only
    for K_tgt in (1, 2, 5):
        r = _at(results.get('H_only', []), K_tgt)
        if r:
            print(f"  {'1h H-series only':<30}  {K_tgt:>3}  ${r['final']:>8.2f}  "
                  f"{100*r['cagr']:+6.1f}%  {r['sharpe_net']:+6.3f}  "
                  f"{100*r['max_dd']:+6.1f}%")

    # Combined
    for K_tgt in (1, 2, 5):
        r = _at(results.get('combined', []), K_tgt)
        if r:
            print(f"  {'Combined D+H':<30}  {K_tgt:>3}  ${r['final']:>8.2f}  "
                  f"{100*r['cagr']:+6.1f}%  {r['sharpe_net']:+6.3f}  "
                  f"{100*r['max_dd']:+6.1f}%")

    # Daily v28 reference
    d = results.get('daily_v28_ref', {})
    if d:
        print(f"\n  {'Daily v28 K=1 (3.3yr ref)':<34}  "
              f"CAGR={100*d['cagr']:+.1f}%  "
              f"Sharpe={d['sharpe']:+.3f}  "
              f"MaxDD={100*d['max_dd']:+.1f}%")

    print("=" * 92)


if __name__ == '__main__':
    main()
