"""
Crypto BSDT v35 — Swing Complement Layer
=========================================
Problem: physics gate is ON only ~47.5% of days. The other ~52.5% (sideways/
ranging regime) is completely idle — zero PnL, wasted opportunity.

Solution: When gate is OFF → deploy swing mean-reversion strategies that trade
BOTH long and short within price ranges. When gate is ON → keep existing v34
trend/directional strategies running unchanged.

                 Gate ON  (47.5% of days)  →  D1-D5 directional + H1-H5 trend
                 Gate OFF (52.5% of days)  →  S1-S5 swing MR (RSI/BB/z-score)

Swing signals (1h resolution):
  S1  ETH  RSI-14 mean-reversion    long < 30, short > 70
  S2  BTC  RSI-14 mean-reversion    long < 30, short > 70
  S3  ETH  Bollinger-20 fade        long at -2σ band, short at +2σ band
  S4  ETH/BTC spread z-score MR     long when spread < -2σ, short > +2σ
  S5  SOL  RSI-14 mean-reversion    (if SOL available)

Gate-complement logic (per 1h bar):
  gate_bar = 1 if that bar's calendar day is a gate-ON day, else 0
  pnl_bar  = gate_bar * pnl_v34[t]  +  (1 - gate_bar) * pnl_swing[t]

Year-by-year breakdown vs v34 baseline at K = 1, 2, 5, 10, 14.
"""
from __future__ import annotations
import os, sys, json, warnings
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
from pathlib import Path
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore')

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

from run_crypto_pairs_v34_full_combined import (
    OUT_DIR, TEST_START, TRAIN_START, TRAIN_END,
    build_1h_df, build_daily_positions,
    upsample_daily_to_1h_pnl,
    compute_1h_strategies, compute_quality, assemble_combined,
    equity_curve, yearly_breakdown, _sigmoid,
)
from run_crypto_pairs_v19 import (
    fetch_and_prepare, add_cross_market_features,
)
from run_crypto_pairs_v30_perp_realism import build_book
from run_crypto_pairs_v27 import compute_unsigned_weights, G_LO, K_LO
from run_crypto_pairs_v28 import (
    build_v28_pnl,
    compute_quality_risk_weights as daily_cqrw,
)

OUT_DIR_ = Path(OUT_DIR)

BPD = 24   # bars per day (1h)


# ═══════════════════════════════════════════════════════════════════════════
#  HELPER: RSI
# ═══════════════════════════════════════════════════════════════════════════

def _rsi(price: pd.Series, window: int = 14 * BPD) -> pd.Series:
    """Wilder RSI on a price series."""
    delta = price.diff()
    gain  = delta.clip(lower=0.0).ewm(span=window, adjust=False).mean()
    loss  = (-delta.clip(upper=0.0)).ewm(span=window, adjust=False).mean()
    rs    = gain / loss.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


# ═══════════════════════════════════════════════════════════════════════════
#  SWING STRATEGIES  (1h, mean-reversion, both long & short)
# ═══════════════════════════════════════════════════════════════════════════

def compute_swing_strategies(df: pd.DataFrame, has_sol: bool,
                              rsi_window_days: int = 14,
                              bb_window_days:  int = 20,
                              zsc_window_days: int = 10,
                              rsi_ob: float   = 70.0,
                              rsi_os: float   = 30.0,
                              bb_sigma: float  = 2.0,
                              zsc_thresh: float = 1.5) -> dict:
    """
    Pure mean-reversion swing strategies.

    All signals are shifted 1 bar (no look-ahead).
    Position is in {-1, 0, +1}; combined MR.

    S1  ETH RSI fade
    S2  BTC RSI fade
    S3  ETH Bollinger-band fade
    S4  ETH/BTC spread z-score fade
    S5  SOL RSI fade  (optional)
    S6  ETH short-window RSI (faster, 6h)
    S7  BTC short-window RSI (faster, 6h)
    """
    rsi_w = int(rsi_window_days * BPD)
    bb_w  = int(bb_window_days  * BPD)
    zsc_w = int(zsc_window_days * BPD)
    fast_w = 6 * BPD   # 6-hour RSI for faster swings

    # ── reconstruct price from cumulative returns ───────────────────────────
    # We use 100 * cumprod(1+ret) as a synthetic price index
    price_eth  = 100.0 * (1.0 + df['ret_eth'].fillna(0.0)).cumprod()
    price_btc  = 100.0 * (1.0 + df['ret_btc'].fillna(0.0)).cumprod()

    # ── S1: ETH RSI-14 fade ─────────────────────────────────────────────────
    rsi_eth = _rsi(price_eth, rsi_w)
    # Long when oversold (<30), short when overbought (>70)
    # Position proportional to distance from midline (50) — soft signal
    pos_s1_raw  = -(rsi_eth - 50.0) / 50.0   # negative: fade the direction
    # Hard-threshold: only enter at extremes
    pos_s1      = pd.Series(0.0, index=df.index)
    pos_s1[rsi_eth < rsi_os] = +1.0           # oversold → long
    pos_s1[rsi_eth > rsi_ob] = -1.0           # overbought → short
    pnl_S1      = pos_s1.shift(1).fillna(0.0) * df['ret_eth']

    # ── S2: BTC RSI-14 fade ─────────────────────────────────────────────────
    rsi_btc = _rsi(price_btc, rsi_w)
    pos_s2      = pd.Series(0.0, index=df.index)
    pos_s2[rsi_btc < rsi_os] = +1.0
    pos_s2[rsi_btc > rsi_ob] = -1.0
    pnl_S2      = pos_s2.shift(1).fillna(0.0) * df['ret_btc']

    # ── S3: ETH Bollinger-band fade ─────────────────────────────────────────
    roll_mu  = price_eth.rolling(bb_w, min_periods=bb_w // 4).mean()
    roll_sd  = price_eth.rolling(bb_w, min_periods=bb_w // 4).std()
    bb_z     = (price_eth - roll_mu) / roll_sd.replace(0.0, np.nan)  # z-score within band
    pos_s3   = pd.Series(0.0, index=df.index)
    pos_s3[bb_z < -bb_sigma] = +1.0   # price at lower band → long
    pos_s3[bb_z >  bb_sigma] = -1.0   # price at upper band → short
    pnl_S3   = pos_s3.shift(1).fillna(0.0) * df['ret_eth']

    # ── S4: ETH/BTC spread z-score MR ───────────────────────────────────────
    spread   = df['spread_ret_eb'].fillna(0.0)
    spread_c = spread.rolling(zsc_w * BPD, min_periods=BPD * 5).sum()   # cumulative spread
    smu      = spread_c.rolling(zsc_w * BPD, min_periods=BPD * 5).mean()
    ssd      = spread_c.rolling(zsc_w * BPD, min_periods=BPD * 5).std()
    sz       = (spread_c - smu) / ssd.replace(0.0, np.nan)
    pos_s4   = pd.Series(0.0, index=df.index)
    pos_s4[sz < -zsc_thresh]  = +1.0   # spread depressed → buy spread (long ETH short BTC)
    pos_s4[sz >  zsc_thresh]  = -1.0   # spread elevated → sell spread
    pnl_S4   = pos_s4.shift(1).fillna(0.0) * df['spread_ret_eb']

    # ── S6: ETH fast RSI (6h) ───────────────────────────────────────────────
    rsi_eth_f = _rsi(price_eth, fast_w)
    pos_s6    = pd.Series(0.0, index=df.index)
    pos_s6[rsi_eth_f < rsi_os] = +1.0
    pos_s6[rsi_eth_f > rsi_ob] = -1.0
    pnl_S6    = pos_s6.shift(1).fillna(0.0) * df['ret_eth']

    # ── S7: BTC fast RSI (6h) ───────────────────────────────────────────────
    rsi_btc_f = _rsi(price_btc, fast_w)
    pos_s7    = pd.Series(0.0, index=df.index)
    pos_s7[rsi_btc_f < rsi_os] = +1.0
    pos_s7[rsi_btc_f > rsi_ob] = -1.0
    pnl_S7    = pos_s7.shift(1).fillna(0.0) * df['ret_btc']

    strats = {
        'S1_rsi_eth':   pnl_S1.fillna(0.0),
        'S2_rsi_btc':   pnl_S2.fillna(0.0),
        'S3_bb_eth':    pnl_S3.fillna(0.0),
        'S4_spread_mr': pnl_S4.fillna(0.0),
        'S6_rsi_eth_f': pnl_S6.fillna(0.0),
        'S7_rsi_btc_f': pnl_S7.fillna(0.0),
    }

    # ── S5: SOL RSI fade ────────────────────────────────────────────────────
    if has_sol and 'ret_sol' in df.columns:
        price_sol = 100.0 * (1.0 + df['ret_sol'].fillna(0.0)).cumprod()
        rsi_sol   = _rsi(price_sol, rsi_w)
        pos_s5    = pd.Series(0.0, index=df.index)
        pos_s5[rsi_sol < rsi_os] = +1.0
        pos_s5[rsi_sol > rsi_ob] = -1.0
        strats['S5_rsi_sol'] = (pos_s5.shift(1).fillna(0.0) * df['ret_sol']).fillna(0.0)

    return strats


# ═══════════════════════════════════════════════════════════════════════════
#  REGIME-SPLIT COMBINER
# ═══════════════════════════════════════════════════════════════════════════

def build_gate_bar(gate_daily: pd.Series, index_1h: pd.Index) -> pd.Series:
    """Map daily gate (bool) to 1h bars. gate=1 → trend regime, 0 → swing regime."""
    g_idx = pd.to_datetime(gate_daily.index).normalize()
    if g_idx.tz is not None:
        g_idx = g_idx.tz_localize(None)
    g_map = pd.Series(gate_daily.astype(float).values, index=g_idx)
    dates = pd.to_datetime(index_1h).normalize()
    return pd.Series([g_map.get(d, 0.0) for d in dates],
                     index=index_1h, dtype=float)


def complement_portfolio(pnl_trend:  pd.Series,
                          pnl_swing:  pd.Series,
                          gate_bar:   pd.Series) -> pd.Series:
    """
    Regime-split PnL:
      gate=1 bars  → trend portfolio
      gate=0 bars  → swing portfolio
    Both series must share the same index.
    """
    g = gate_bar.reindex(pnl_trend.index, fill_value=0.0)
    p_t = pnl_trend.reindex(pnl_trend.index, fill_value=0.0)
    p_s = pnl_swing.reindex(pnl_trend.index, fill_value=0.0)
    return g * p_t + (1.0 - g) * p_s


# ═══════════════════════════════════════════════════════════════════════════
#  YEAR-BY-YEAR TABLE  (reused from v34_yoy)
# ═══════════════════════════════════════════════════════════════════════════

def _net_ret(pnl: pd.Series, K: float, bpd: int, tcost: float = 5.0) -> pd.Series:
    fee = (tcost / 1e4 / bpd) * (pnl.fillna(0.0).abs() > 1e-12).astype(float)
    return pnl.fillna(0.0) * float(K) - fee


def _yr(r: pd.Series, bpd: int) -> dict:
    eq  = (1.0 + r).cumprod()
    return {'ret': float((1.0 + r).prod() - 1.0),
            'mdd': float((eq / eq.cummax() - 1.0).min()),
            'sh':  float(r.mean() / r.std() * np.sqrt(252.0 * bpd)) if r.std() > 0 else 0.0,
            'act': float((r.abs() > 1e-12).sum()) / bpd}


def yoy_table(label: str, pnl: pd.Series, K_list: list, bpd: int = 24) -> dict:
    print(f"\n{'═'*100}")
    print(f"  {label}")
    print(f"{'═'*100}")
    out_data: dict[str, list] = {}
    for K in K_list:
        r_full = _net_ret(pnl, K, bpd)
        eq = 100.0
        rows = []
        for yr in [2023, 2024, 2025, 2026]:
            mask = pnl.index.year == yr
            if not mask.any(): continue
            s = _yr(r_full[mask], bpd)
            start = eq; eq = eq * (1.0 + s['ret'])
            rows.append({'year': yr, 'start': start, 'ret': s['ret'] * 100,
                         'profit': eq - start, 'end': eq,
                         'mdd': s['mdd'] * 100, 'sh': s['sh'], 'act': s['act']})

        first_yr = pnl[pnl.index.year >= 2023].index[0]
        total_yr = (pnl.index[-1] - first_yr).days / 365.0
        cagr     = (eq / 100.0) ** (1.0 / max(total_yr, 0.1)) - 1.0

        print(f"\n  ── K = {K}   (start $100.00) ──")
        print(f"  {'Year':<6}  {'Start $':>9}  {'Return':>8}  {'Profit $':>9}  "
              f"{'End $':>9}  {'MaxDD':>7}  {'Sharpe':>7}  {'Active':>8}")
        print(f"  {'-'*6}  {'-'*9}  {'-'*8}  {'-'*9}  {'-'*9}  {'-'*7}  {'-'*7}  {'-'*8}")
        for r in rows:
            print(f"  {r['year']:<6}  ${r['start']:>8.2f}  {r['ret']:>+7.1f}%  "
                  f"${r['profit']:>+8.2f}  ${r['end']:>8.2f}  "
                  f"{r['mdd']:>+6.1f}%  {r['sh']:>+6.2f}  {r['act']:>7.0f}d")
        print(f"  {'TOTAL':<6}  $  100.00  {100*(eq/100-1):>+7.1f}%  "
              f"${eq-100:>+8.2f}  ${eq:>8.2f}  {'─'*7}  {'─'*7}  "
              f"CAGR = {100*cagr:>+.1f}%/yr")
        out_data[f'K{K}'] = rows
    return out_data


def compact_row(label: str, pnl: pd.Series, K_list: list, bpd: int):
    """Single header row per config for the summary table."""
    rows = []
    for K in K_list:
        r_full = _net_ret(pnl, K, bpd)
        eq = 100.0; yr_r = {}
        for yr in [2023, 2024, 2025, 2026]:
            mask = pnl.index.year == yr
            if not mask.any(): continue
            ret = float((1 + r_full[mask]).prod() - 1.0); yr_r[yr] = ret; eq *= (1 + ret)
        all_eq  = 100.0 * (1 + r_full).cumprod()
        mdd_all = float((all_eq / all_eq.cummax() - 1).min())
        first_yr = pnl[pnl.index.year >= 2023].index[0]
        cagr = (eq / 100.0) ** (1.0 / max((pnl.index[-1] - first_yr).days / 365.0, 0.1)) - 1.0
        def f(y): return f"{100*yr_r[y]:>+5.0f}%" if y in yr_r else "  ─  "
        rows.append(f"  K={K:<2}  {f(2023):>7}  {f(2024):>7}  {f(2025):>7}  {f(2026):>7}  "
                    f"${eq:>8.2f}  {100*mdd_all:>+5.1f}%  {100*cagr:>+5.1f}%/yr")
    print(f"\n  {label}")
    for r in rows:
        print(r)


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print("=" * 100)
    print("  CRYPTO BSDT v35 — SWING COMPLEMENT LAYER")
    print("  Gate ON  → v34 trend strategies  (D1-D5 + H1-H5)")
    print("  Gate OFF → swing MR strategies   (S1-S7: RSI/BB/spread, long & short)")
    print("  Full-regime coverage: idle time is now swing capital")
    print("=" * 100)

    # ─────────────────────────────────────────── 1h DATA ──
    print("\n[1] Fetching Binance 1h klines ...")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_1h = df_1h.index >= TEST_START

    # ─────────────────────────────────────── H1-H5 TREND ──
    print("\n[2] Computing trend strategies (H1-H5) ...")
    h_strats = compute_1h_strategies(df_1h, has_sol)

    # ─────────────────────────────────── DAILY PIPELINE ──
    print("\n[3] Daily physics pipeline ...")
    df_d    = fetch_and_prepare()
    df_d    = add_cross_market_features(df_d)
    from run_crypto_pairs_v19 import fetch_binance_funding as _fbf, add_leverage_features
    fund    = _fbf(symbols=['ETHUSDT','BTCUSDT'], start='2020-06-01')
    df_d    = add_leverage_features(df_d, fund)

    tmask_d   = (df_d.index >= TRAIN_START) & (df_d.index <= TRAIN_END)
    tmask_arr = np.asarray(tmask_d, dtype=bool)
    test_d    = df_d.index >= TEST_START

    pos_dict, _, F_daily, gate_daily = build_daily_positions(df_d, tmask_d, tmask_arr)

    n_on  = int(gate_daily[test_d].sum())
    n_tot = int(test_d.sum())
    print(f"  Gate ON: {n_on}/{n_tot} days ({100*n_on/n_tot:.1f}%)   "
          f"Gate OFF (swing days): {n_tot-n_on} ({100*(1-n_on/n_tot):.1f}%)")

    # ─────────────────────────────── UPSAMPLE DAILY → 1h ──
    print("\n[4] Upsampling daily → 1h ...")
    instr_map = {
        'D1_trend_eth': df_1h['ret_eth'],
        'D2_pairs_eb':  df_1h['spread_ret_eb'],
        'D3_pairs_es':  df_1h['ret_eth'] - df_1h.get('ret_sol', df_1h['ret_eth']),
        'D4_macro_btc': df_1h['ret_btc'],
        'D5_macro_alt': df_1h['ret_eth'],
    }
    d_strats_1h = {name: upsample_daily_to_1h_pnl(pos, instr_map.get(name, df_1h['ret_eth']), gate_daily)
                   for name, pos in pos_dict.items()}

    # ─────────────────────────────── v34 TREND PORTFOLIO ──
    print("\n[5] Building v34 trend portfolio ...")
    all_pnls_v34 = {**d_strats_1h, **h_strats}
    Q_v34        = compute_quality(all_pnls_v34, bpd=BPD)
    pnl_v34      = assemble_combined(all_pnls_v34, Q_v34)

    ann_1h = 252.0 * BPD
    sh_v34 = float(pnl_v34[test_1h].mean() / pnl_v34[test_1h].std() * np.sqrt(ann_1h))
    act_v34 = float((pnl_v34[test_1h].abs() > 1e-12).sum()) / BPD
    print(f"  v34 baseline — gross Sharpe: {sh_v34:+.2f}   Active: {act_v34:.0f}d")

    # ─────────────────────────────────── SWING STRATEGIES ──
    print("\n[6] Computing swing MR strategies (S1-S7) ...")
    s_strats = compute_swing_strategies(df_1h, has_sol)

    # Show standalone swing stats
    print(f"\n  Swing strategy standalone (test 2023→2026, no gate filter):")
    print(f"  {'name':<16}  {'Sharpe':>8}  {'Active':>8}  {'Long%':>7}  {'Short%':>7}")
    print(f"  {'-'*16}  {'-'*8}  {'-'*8}  {'-'*7}  {'-'*7}")
    for k, p in s_strats.items():
        pt = p[test_1h].fillna(0.0)
        if pt.std() < 1e-12: continue
        sh   = float(pt.mean() / pt.std() * np.sqrt(ann_1h))
        act  = float((pt.abs() > 1e-12).sum()) / BPD
        # Recover position series to get long/short %
        # pos was: pnl = pos * ret → but we can't recover cleanly; proxy via sign of PnL
        long_pct  = float((pt > 1e-12).sum()) / max(int((pt.abs() > 1e-12).sum()), 1) * 100
        short_pct = float((pt < -1e-12).sum()) / max(int((pt.abs() > 1e-12).sum()), 1) * 100
        print(f"  {k:<16}  {sh:>+8.3f}  {act:>7.0f}d  {long_pct:>6.1f}%  {short_pct:>6.1f}%")

    # Swing portfolio (quality-gated internally)
    Q_sw      = compute_quality(s_strats, bpd=BPD, sh_d=30, vol_d=20)
    pnl_swing = assemble_combined(s_strats, Q_sw)

    sh_sw  = float(pnl_swing[test_1h].mean() / pnl_swing[test_1h].std() * np.sqrt(ann_1h)) \
             if pnl_swing[test_1h].std() > 0 else 0
    act_sw = float((pnl_swing[test_1h].abs() > 1e-12).sum()) / BPD
    print(f"\n  Swing portfolio (unfiltered) — gross Sharpe: {sh_sw:+.2f}   Active: {act_sw:.0f}d")

    # ────────────────────────── GATE-COMPLEMENT PORTFOLIO ──
    print("\n[7] Building gate-complement (v35) portfolio ...")
    gate_bar = build_gate_bar(gate_daily, df_1h.index)

    # v35: trend during gate-ON, swing during gate-OFF
    pnl_v35 = complement_portfolio(pnl_v34, pnl_swing, gate_bar)

    sh_v35  = float(pnl_v35[test_1h].mean() / pnl_v35[test_1h].std() * np.sqrt(ann_1h)) \
              if pnl_v35[test_1h].std() > 0 else 0
    act_v35 = float((pnl_v35[test_1h].abs() > 1e-12).sum()) / BPD
    print(f"  v35 combined — gross Sharpe: {sh_v35:+.2f}   Active: {act_v35:.0f}d")
    print(f"  Coverage gain vs v34: {act_v35 - act_v34:+.0f}d ({100*(act_v35 - act_v34)/max(act_v34,1):+.1f}%)")

    # Also build a BLENDED version: 50% trend + 50% swing (always-on)
    pnl_blend = 0.5 * pnl_v34 + 0.5 * pnl_swing
    sh_bl = float(pnl_blend[test_1h].mean() / pnl_blend[test_1h].std() * np.sqrt(ann_1h)) \
            if pnl_blend[test_1h].std() > 0 else 0
    print(f"  Blended (50/50 always-on) — gross Sharpe: {sh_bl:+.2f}")

    # ─────────────────────── YEAR-BY-YEAR COMPARISON ──────
    K_LIST = [1, 2, 5, 10, 14]
    pnl_v34_t = pnl_v34[test_1h]
    pnl_v35_t = pnl_v35[test_1h]
    pnl_bl_t  = pnl_blend[test_1h]
    pnl_sw_t  = pnl_swing[test_1h]

    results = {}

    results['v34_trend_only'] = yoy_table(
        "v34 BASELINE  [trend-only, gate-idle days = $0 PnL]",
        pnl_v34_t, K_LIST, bpd=BPD)

    results['v35_complement'] = yoy_table(
        "v35 SWING COMPLEMENT  [trend when gate ON, MR swings when gate OFF]",
        pnl_v35_t, K_LIST, bpd=BPD)

    results['v35_swing_only'] = yoy_table(
        "SWING-ONLY PORTFOLIO  [RSI/BB/spread mean-reversion, both long & short]",
        pnl_sw_t, K_LIST, bpd=BPD)

    results['v35_blend_5050'] = yoy_table(
        "BLENDED 50/50  [always-on: 50% v34 trend + 50% swing MR]",
        pnl_bl_t, K_LIST, bpd=BPD)

    # ─────────────────────────── QUICK SUMMARY TABLE ──────
    print(f"\n\n{'═'*100}")
    print("  QUICK SUMMARY — Year returns per K level")
    print(f"  {'':5}  {'2023':>7}  {'2024':>7}  {'2025':>7}  {'2026YTD':>7}  {'$100→':>9}  {'MaxDD':>7}  {'CAGR':>9}")
    print(f"{'═'*100}")
    compact_row("v34 BASELINE  (trend-only)",            pnl_v34_t, K_LIST, BPD)
    compact_row("v35 COMPLEMENT (trend + swing by regime)", pnl_v35_t, K_LIST, BPD)
    compact_row("SWING ONLY  (MR long/short)",            pnl_sw_t,  K_LIST, BPD)
    compact_row("BLEND 50/50  (always-on)",               pnl_bl_t,  K_LIST, BPD)

    # ─────────────────────── SAVE ──
    out_path = OUT_DIR_ / 'crypto_bsdt_v35_swing_complement.json'
    with open(out_path, 'w') as fh:
        json.dump(results, fh, indent=2, default=float)
    print(f"\n  Saved → {out_path}")
    print("=" * 100)


if __name__ == '__main__':
    main()
