"""
Crypto BSDT v34 — Year-on-Year P&L Calculator
==============================================
Computes year-by-year compounding equity from $100 starting capital
for the full combined system (D1-D5 + H1-H5), H-only, and daily v28 reference.

Shows:
  - Per-year return (%), MaxDD (%), Sharpe, Active days
  - Running dollar equity balance (compounding from $100)
  - Multiple K levels: 1, 2, 5, 10, 14
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

# Import everything we need from v34 — avoids repeating the full pipeline
from run_crypto_pairs_v34_full_combined import (
    OUT_DIR,
    TEST_START, TRAIN_START, TRAIN_END,
    build_1h_df,
    build_daily_positions,
    upsample_daily_to_1h_pnl,
    compute_1h_strategies,
    compute_quality,
    assemble_combined,
    equity_curve,
)
# v28 daily reference pieces
from run_crypto_pairs_v19 import (
    fetch_and_prepare, add_cross_market_features,
    fetch_binance_funding, add_leverage_features,
    simulate_from_pnl,
)
from run_crypto_pairs_v30_perp_realism import build_book
from run_crypto_pairs_v27 import compute_unsigned_weights, G_LO, K_LO
from run_crypto_pairs_v28 import (
    build_v28_pnl,
    compute_quality_risk_weights as daily_cqrw,
)

OUT_DIR_ = Path(OUT_DIR)


# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _net_ret(pnl: pd.Series, K: float, bpd: int, tcost_bps: float = 5.0) -> pd.Series:
    fee = (tcost_bps / 1e4 / bpd) * (pnl.fillna(0.0).abs() > 1e-12).astype(float)
    return pnl.fillna(0.0) * float(K) - fee


def _yr_stats(r: pd.Series, bpd: int) -> dict:
    eq   = (1.0 + r).cumprod()
    mdd  = float((eq / eq.cummax() - 1.0).min())
    ret  = float((1.0 + r).prod() - 1.0)
    sh   = float(r.mean() / r.std() * np.sqrt(252.0 * bpd)) if r.std() > 0 else 0.0
    act  = float((r.abs() > 1e-12).sum()) / bpd
    return {'ret': ret, 'mdd': mdd, 'sh': sh, 'act': act}


def print_yoy_table(label: str, pnl: pd.Series, K_list: list,
                    bpd: int = 24, init: float = 100.0) -> dict:
    """
    Detailed year-by-year compounding equity table.
    Returns serialisable dict {K: [row, ...]} for JSON dump.
    """
    print(f"\n{'═'*100}")
    print(f"  {label}")
    print(f"{'═'*100}")

    out_data: dict[str, list] = {}

    for K in K_list:
        r_full = _net_ret(pnl, K, bpd)
        eq     = init
        rows   = []

        for yr in [2023, 2024, 2025, 2026]:
            mask = pnl.index.year == yr
            if not mask.any():
                continue
            s = _yr_stats(r_full[mask], bpd)
            start_eq = eq
            eq = eq * (1.0 + s['ret'])
            rows.append({'year': yr, 'start_eq': start_eq,
                         'ret_pct': s['ret'] * 100, 'profit': eq - start_eq,
                         'end_eq': eq, 'mdd_pct': s['mdd'] * 100,
                         'sharpe': s['sh'], 'active_d': s['act']})

        # Overall CAGR
        total_yr = (pnl.index[-1] - pnl[pnl.index.year >= 2023].index[0]).days / 365.0
        cagr     = (eq / init) ** (1.0 / max(total_yr, 0.1)) - 1.0

        print(f"\n  ── K = {K}   (start $100.00) ──")
        print(f"  {'Year':<6}  {'Start $':>9}  {'Return':>8}  {'Profit $':>9}  "
              f"{'End $':>9}  {'MaxDD':>7}  {'Sharpe':>7}  {'ActiveDays':>10}")
        print(f"  {'-'*6}  {'-'*9}  {'-'*8}  {'-'*9}  {'-'*9}  "
              f"{'-'*7}  {'-'*7}  {'-'*10}")
        for r in rows:
            print(f"  {r['year']:<6}  "
                  f"${r['start_eq']:>8.2f}  "
                  f"{r['ret_pct']:>+7.1f}%  "
                  f"${r['profit']:>+8.2f}  "
                  f"${r['end_eq']:>8.2f}  "
                  f"{r['mdd_pct']:>+6.1f}%  "
                  f"{r['sharpe']:>+6.2f}  "
                  f"{r['active_d']:>9.0f}d")
        print(f"  {'TOTAL':<6}  ${init:>8.2f}  "
              f"{100*(eq/init-1):>+7.1f}%  "
              f"${eq-init:>+8.2f}  "
              f"${eq:>8.2f}  "
              f"{'─'*7}  {'─'*7}  "
              f"CAGR = {100*cagr:+.1f}%/yr")

        out_data[f'K{K}'] = rows

    return out_data


def compact_summary(label: str, pnl: pd.Series, K_list: list, bpd: int = 24):
    """One-liner per K: 2023 / 2024 / 2025 / 2026YTD → Final $ → CAGR"""
    print(f"\n  {label}")
    print(f"  {'K':>3}  {'2023':>8}  {'2024':>8}  {'2025':>8}  {'2026YTD':>9}  "
          f"{'$100→':>9}  {'MaxDD':>7}  {'CAGR':>8}")
    print(f"  {'-'*3}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*9}  {'-'*9}  {'-'*7}  {'-'*8}")
    for K in K_list:
        r_full = _net_ret(pnl, K, bpd)
        eq = 100.0
        yr_r: dict[int, float] = {}
        for yr in [2023, 2024, 2025, 2026]:
            mask = pnl.index.year == yr
            if not mask.any():
                continue
            ret = float((1 + r_full[mask]).prod() - 1.0)
            yr_r[yr] = ret
            eq *= (1 + ret)
        all_eq  = 100.0 * (1 + r_full).cumprod()
        mdd_all = float((all_eq / all_eq.cummax() - 1).min())
        cagr    = (eq / 100.0) ** (1.0 / max(
                    (pnl.index[-1] - pnl[pnl.index.year >= 2023].index[0]).days / 365.0,
                    0.1)) - 1.0
        def fmt(y): return f"{100*yr_r[y]:>+6.0f}%" if y in yr_r else "  ─ "
        print(f"  {K:>3}  {fmt(2023):>8}  {fmt(2024):>8}  {fmt(2025):>8}  {fmt(2026):>9}  "
              f"${eq:>8.2f}  {100*mdd_all:>+6.1f}%  {100*cagr:>+6.1f}%/yr")


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print("=" * 100)
    print("  CRYPTO BSDT v34 — YEAR-ON-YEAR PROFIT BREAKDOWN")
    print("  Starting capital: $100  |  Fee: 5 bps/active bar  |  Compounding")
    print("=" * 100)

    # ─────────────────────────────────────────── 1. BINANCE 1h DATA ──
    print("\n[1] Fetching Binance 1h kline history ...")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_1h = df_1h.index >= TEST_START

    # ─────────────────────────────────────── 2. 1h STRATEGIES H1-H5 ──
    print("\n[2] Computing 1h intraday strategies (H1–H5) ...")
    h_strats = compute_1h_strategies(df_1h, has_sol)

    # ─────────────────────────────────────── 3. DAILY PIPELINE D1-D5 ──
    print("\n[3] Daily v28 pipeline (positions + physics gate) ...")
    df_d   = fetch_and_prepare()
    df_d   = add_cross_market_features(df_d)
    funding = fetch_binance_funding(symbols=['ETHUSDT','BTCUSDT'], start='2020-06-01')
    df_d   = add_leverage_features(df_d, funding)

    tmask_d   = (df_d.index >= TRAIN_START) & (df_d.index <= TRAIN_END)
    tmask_arr = np.asarray(tmask_d, dtype=bool)
    test_d    = df_d.index >= TEST_START

    pos_dict, _, F_daily, gate_daily = build_daily_positions(df_d, tmask_d, tmask_arr)

    # Daily v28 reference PnL
    strats_v28, _, _, _ = build_book(df_d, tmask_d, tmask_arr)
    W_d   = compute_unsigned_weights(F_daily, use_activation=True, g_lo=G_LO, k_lo=K_LO)
    Q_d   = daily_cqrw(strats_v28, vol_win=60, sharpe_win=120, sharpe_k=2.0)
    lev_d = pd.Series(1.0, index=df_d.index)
    pnl_v28_daily = build_v28_pnl(strats_v28, W_d, Q_d, lev_d, df_d.index)
    pnl_v28 = pnl_v28_daily[test_d]

    # ─────────────────────────────────────── 4. UPSAMPLE DAILY → 1h ──
    print("\n[4] Upsampling daily positions to 1h bars ...")
    instr_map = {
        'D1_trend_eth': df_1h['ret_eth'],
        'D2_pairs_eb':  df_1h['spread_ret_eb'],
        'D3_pairs_es':  (df_1h['ret_eth'] - df_1h.get('ret_sol', df_1h['ret_eth'])),
        'D4_macro_btc': df_1h['ret_btc'],
        'D5_macro_alt': df_1h['ret_eth'],
    }
    d_strats_1h = {name: upsample_daily_to_1h_pnl(pos, instr_map.get(name, df_1h['ret_eth']), gate_daily)
                   for name, pos in pos_dict.items()}

    # ─────────────────────────────────────── 5. ASSEMBLE PORTFOLIOS ──
    print("\n[5] Assembling portfolios ...")
    all_pnls     = {**d_strats_1h, **h_strats}
    pnl_combined = assemble_combined(all_pnls, compute_quality(all_pnls, bpd=24))[test_1h]

    Q_h      = compute_quality(h_strats, bpd=24)
    pnl_h    = assemble_combined(h_strats, pd.DataFrame({k: Q_h[k] for k in h_strats if k in Q_h.columns}))[test_1h]

    ann_1h = 252.0 * 24
    sh_c = float(pnl_combined.mean() / pnl_combined.std() * np.sqrt(ann_1h)) if pnl_combined.std() > 0 else 0
    sh_h = float(pnl_h.mean() / pnl_h.std() * np.sqrt(ann_1h)) if pnl_h.std() > 0 else 0
    print(f"  Combined gross Sharpe: {sh_c:+.2f}   H-only gross Sharpe: {sh_h:+.2f}")

    # ─────────────────────── 6. YEAR-BY-YEAR DETAILED TABLES ──────────
    K_LIST_1H    = [1, 2, 5, 10, 14]
    K_LIST_DAILY = [1, 5, 14, 29]

    all_json = {}

    all_json['combined'] = print_yoy_table(
        "COMBINED SYSTEM  [D1-D5 physics-gated daily + H1-H5 quality-gated 1h]",
        pnl_combined, K_LIST_1H, bpd=24)

    all_json['h_only'] = print_yoy_table(
        "H-ONLY SYSTEM  [H1-H5 quality-gated 1h, no physics gate]",
        pnl_h, K_LIST_1H, bpd=24)

    all_json['daily_v28'] = print_yoy_table(
        "DAILY v28_full_no_brk  [benchmark — 1 bar = 1 trading day]",
        pnl_v28, K_LIST_DAILY, bpd=1)

    # ──────────────────────── 7. COMPACT QUICK-REFERENCE SUMMARY ──────
    print(f"\n\n{'═'*100}")
    print("  QUICK-REFERENCE SUMMARY  — year-by-year return at each K level")
    print(f"{'═'*100}")

    compact_summary("Combined D+H (1h system)", pnl_combined, K_LIST_1H, bpd=24)
    compact_summary("H-only (1h system)",        pnl_h,        K_LIST_1H, bpd=24)
    compact_summary("Daily v28 (benchmark)",      pnl_v28,      K_LIST_DAILY, bpd=1)

    # ─────────────────────────────────────────────────── SAVE JSON ──
    out_path = OUT_DIR_ / 'crypto_bsdt_v34_yoy_profit.json'
    with open(out_path, 'w') as fh:
        json.dump(all_json, fh, indent=2, default=float)
    print(f"\n  Results saved → {out_path}")
    print("=" * 100)


if __name__ == '__main__':
    main()

