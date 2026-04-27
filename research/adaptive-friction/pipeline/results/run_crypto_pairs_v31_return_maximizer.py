"""
Crypto BSDT v31 - RETURN MAXIMIZER
====================================
Goal: find the highest-return config starting from $100.

Two levers:
  1. Leverage K  (K=1 to 50, fine grid)
  2. Activity    (alpha = gated-to-always-on blend: 1.0 / 0.9 / 0.0)

Three activity configs:
  SELECTIVE  alpha=1.0  →  112 active days (production peak Sharpe)
  BLENDED    alpha=0.9  →  275 active days (robust live)
  FULL       alpha=0.0  →  275 active days, no gate (always-on Q+vol)

For each config × K: compute net PnL after directional funding + 5bp fees.
Find Kelly-optimal K (without DD floor) and best K under DD<= {10%,20%,40%}.

Also reports:
  - Kelly fraction approximation (half-Kelly, full-Kelly)
  - Annualized return at optimal K
  - $100 equity scenario
"""
from __future__ import annotations
import os, sys, json
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
from pathlib import Path
import numpy as np
import pandas as pd

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
    get_daily_pnl, compute_cs_weights, simulate_from_pnl,
    _build_state_panel,
    TRAIN_START, TRAIN_END, TEST_START, OUT_DIR, GAMMA_SCORE_WIN,
)
from run_crypto_pairs_v22 import (
    calibrate_frozen_engine, patch_precursor_scale, emit_global_signals,
)
from run_crypto_pairs_v27 import compute_unsigned_weights
from run_crypto_pairs_v28 import (
    compute_quality_risk_weights, build_v28_pnl, V28_KEYS, V28_WCOLS,
)
from run_crypto_pairs_v30_perp_realism import (
    build_book, compute_funding_costs, equity_curve,
)


# =====================================================================
#   KELLY ESTIMATE
# =====================================================================

def kelly_fraction(daily_pnl: pd.Series) -> dict:
    """Discrete Kelly for daily returns (log approximation)."""
    r = daily_pnl[daily_pnl.abs() > 1e-9].values
    mu  = r.mean()
    var = r.var()
    full_kelly = mu / var if var > 0 else 0.0
    return {
        'mean_bps':     float(1e4 * mu),
        'std_bps':      float(1e4 * r.std()),
        'sharpe_daily': float(mu / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0,
        'full_kelly_K': float(full_kelly),
        'half_kelly_K': float(full_kelly / 2.0),
    }


# =====================================================================
#   RETURN SWEEP
# =====================================================================

def return_sweep(pnl_gross: pd.Series, fund_directional: pd.Series,
                 test_mask, tag: str, init: float = 100.0,
                 K_grid=None) -> list[dict]:
    if K_grid is None:
        K_grid = np.concatenate([
            np.arange(1, 10, 0.5),
            np.arange(10, 30, 1),
            np.arange(30, 52, 2),
        ])
    rows = []
    for K in K_grid:
        m = equity_curve(pnl_gross[test_mask], fund_directional[test_mask],
                          K=float(K), init=init, tcost_bps=5.0)
        act = int(pnl_gross[test_mask].abs().gt(1e-9).sum())
        rows.append({
            'tag': tag, 'K': float(K),
            'final': m['final'], 'pnl_dollar': m['pnl_dollar'],
            'cagr': m['cagr'], 'sharpe_net': m['sharpe_net'],
            'max_dd': m['max_dd'], 'active': act,
        })
    return rows


def best_at_dd_limit(rows: list[dict], dd_limit: float) -> dict | None:
    candidates = [r for r in rows if r['max_dd'] >= -dd_limit]
    if not candidates:
        return None
    return max(candidates, key=lambda r: r['cagr'])


# =====================================================================
#   MAIN
# =====================================================================

def main():
    out_dir = Path(OUT_DIR); out_dir.mkdir(parents=True, exist_ok=True)
    print("=" * 100)
    print("  v31 RETURN MAXIMIZER - $100 starting fund, K sweep, 3 activity configs")
    print("=" * 100)

    print("\n[1] Loading + building strategies ...")
    df = fetch_and_prepare()
    df = add_cross_market_features(df)
    funding = fetch_binance_funding(symbols=['ETHUSDT','BTCUSDT'], start='2020-06-01')
    df = add_leverage_features(df, funding)
    train_mask     = (df.index >= TRAIN_START) & (df.index <= TRAIN_END)
    test_mask      = df.index >= TEST_START
    train_mask_arr = np.asarray(train_mask, dtype=bool)

    strats, F, pos_trend, lev_v18s = build_book(df, train_mask, train_mask_arr)

    Q = compute_quality_risk_weights(strats)
    W_gated = compute_unsigned_weights(F, use_activation=True, g_lo=0.50, k_lo=0.30)
    W_open  = compute_unsigned_weights(F, use_activation=False)
    flat    = pd.Series(1.0, index=F.index)

    def make_pnl(alpha):
        """Build gross PnL for a given gate blend alpha=1 gated, alpha=0 always-on."""
        pnl_gated = build_v28_pnl(strats, W_gated, Q, flat, F.index)
        pnl_open  = build_v28_pnl(strats, W_open,  Q, flat, F.index)
        return alpha * pnl_gated + (1 - alpha) * pnl_open

    # Build effective weights for funding (per production gated config)
    W_lag = W_gated.shift(1).fillna(0.0)
    eff = pd.DataFrame(0.0, index=F.index, columns=V28_KEYS)
    for c, k in zip(V28_WCOLS, V28_KEYS):
        eff[k] = W_lag[c] * Q[k]
    s = eff.sum(axis=1).replace(0.0, np.nan)
    eff_norm = eff.div(s, axis=0).fillna(0.0)
    fund = compute_funding_costs(df, eff_norm, pos_trend)
    fund_dir = fund['directional']   # most realistic

    configs = {
        'SELECTIVE (alpha=1.0, 112d)':  (make_pnl(1.0), 1.0),
        'BLENDED   (alpha=0.9, 275d)':  (make_pnl(0.9), 0.9),
        'ALWAYS-ON (alpha=0.0, 275d)':  (make_pnl(0.0), 0.0),
    }

    print("\n" + "=" * 100)
    print("  KELLY ESTIMATES (on active days)")
    print("=" * 100)
    print(f"\n  {'config':<32}  {'mean_bps':>9}  {'std_bps':>8}  "
          f"{'sharpe':>7}  {'full_K':>8}  {'half_K':>8}")
    kelly_info = {}
    for name, (pgross, _) in configs.items():
        ki = kelly_fraction(pgross[test_mask])
        kelly_info[name] = ki
        print(f"  {name:<32}  {ki['mean_bps']:+9.3f}  {ki['std_bps']:>8.3f}  "
              f"{ki['sharpe_daily']:+7.3f}  {ki['full_kelly_K']:>8.1f}  "
              f"{ki['half_kelly_K']:>8.1f}")

    print("\n  Note: full Kelly maximises log-wealth but causes -50% DD on average.")
    print("  Practical range: 1/4-Kelly to 1/2-Kelly is typical hedge-fund usage.")

    # =================================================================
    #   FULL K SWEEP
    # =================================================================
    all_sweep = {}
    for name, (pgross, alpha) in configs.items():
        print(f"\n{'─'*100}")
        print(f"  SWEEP: {name}")
        print(f"{'─'*100}")
        print(f"  {'K':>6}  {'final$':>9}  {'pnl$':>8}  {'cagr%':>7}  "
              f"{'sharpe':>8}  {'maxdd%':>8}")
        rows = return_sweep(pgross, fund_dir, test_mask, tag=name)
        all_sweep[name] = rows
        # Print select K values
        highlights = {1.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0}
        for r in rows:
            if r['K'] in highlights:
                print(f"  {r['K']:>6.0f}  ${r['final']:>8.2f}  ${r['pnl_dollar']:+7.2f}  "
                      f"{100*r['cagr']:+6.2f}%  {r['sharpe_net']:+8.3f}  "
                      f"{100*r['max_dd']:+7.2f}%")

    # =================================================================
    #   BEST K UNDER DD CONSTRAINTS
    # =================================================================
    print("\n" + "=" * 100)
    print("  OPTIMAL K UNDER DRAWDOWN LIMITS  (max return, $100 starting fund)")
    print("=" * 100)
    print(f"\n  {'config':<32}  {'DD_limit':>8}  {'K':>6}  {'final$':>9}  "
          f"{'cagr%':>7}  {'sharpe':>8}  {'maxdd%':>8}")
    best_rows = []
    for name, rows in all_sweep.items():
        for dd_lim in (0.10, 0.20, 0.30, 0.40, 0.99):
            b = best_at_dd_limit(rows, dd_lim)
            if b:
                flag = ''
                if dd_lim == 0.99:
                    flag = ' (no cap)'
                print(f"  {name:<32}  {dd_lim:>7.0%}  {b['K']:>6.1f}  "
                      f"${b['final']:>8.2f}  {100*b['cagr']:+6.2f}%  "
                      f"{b['sharpe_net']:+8.3f}  {100*b['max_dd']:+7.2f}%{flag}")
                best_rows.append({**b, 'dd_limit': dd_lim})

    # =================================================================
    #   HEADLINE: single best config for high return
    # =================================================================
    print("\n" + "=" * 100)
    print("  RECOMMENDED HIGH-RETURN CONFIGS ($100 → ?, 3.3y test)")
    print("=" * 100)
    # Find top results by final$ across all configs and DD limits
    all_bests = []
    for name, rows in all_sweep.items():
        ki = kelly_info[name]
        for dd_lim, label in [(0.10,'conservative'), (0.20,'moderate'),
                               (0.30,'aggressive'), (0.40,'high_risk')]:
            b = best_at_dd_limit(rows, dd_lim)
            if b:
                all_bests.append({**b, 'dd_limit': dd_lim, 'risk_label': label,
                                  'kelly_ratio': b['K'] / max(ki['full_kelly_K'], 0.01)})

    all_bests.sort(key=lambda x: x['final'], reverse=True)
    print(f"\n  {'rank':>4}  {'config':<30}  {'K':>6}  {'DD_lim':>7}  "
          f"{'final$':>9}  {'cagr%':>7}  {'maxdd%':>8}  {'kelly_frac':>11}")
    for i, b in enumerate(all_bests[:12], 1):
        print(f"  {i:>4}  {b['tag']:<30}  {b['K']:>6.1f}  {b['dd_limit']:>7.0%}  "
              f"${b['final']:>8.2f}  {100*b['cagr']:+6.2f}%  "
              f"{100*b['max_dd']:+7.2f}%  {b['kelly_ratio']:>10.2f}x")

    print("\n  * Kelly ratio: K / full-Kelly (1.0 = full Kelly, 0.5 = half-Kelly)")
    print("  * Typical target: 0.25–0.50x Kelly for risk-adjusted live trading")

    # =================================================================
    #   YEARLY EQUITY for top 3 configs
    # =================================================================
    print("\n" + "=" * 100)
    print("  YEARLY PATH for top 3 configs")
    print("=" * 100)
    seen = set()
    top3_configs = []
    for b in all_bests:
        key = b['tag']
        if key not in seen:
            seen.add(key)
            top3_configs.append(b)
        if len(top3_configs) == 3:
            break

    for b in top3_configs:
        alpha_val = 1.0 if 'alpha=1.0' in b['tag'] else (0.9 if 'alpha=0.9' in b['tag'] else 0.0)
        pgross = make_pnl(alpha_val)
        m = equity_curve(pgross[test_mask], fund_dir[test_mask], K=b['K'],
                          init=100.0, tcost_bps=5.0)
        eq = m['eq_curve']
        print(f"\n  {b['tag']}  K={b['K']}  (final=${m['final']:.2f}):")
        print(f"  {'year':>5}  {'start$':>9}  {'end$':>9}  {'pnl$':>9}  {'pnl%':>7}")
        for y, sub in eq.groupby(eq.index.year):
            if len(sub) < 5:
                continue
            s, e = sub.iloc[0], sub.iloc[-1]
            print(f"  {int(y):>5}  ${s:>8.2f}  ${e:>8.2f}  "
                  f"${e-s:+8.2f}  {100*(e/s-1):+6.2f}%")

    # SAVE
    jp = Path(OUT_DIR) / 'crypto_bsdt_v31_return_maximizer.json'
    out = {
        'kelly_estimates':      {k: v for k, v in kelly_info.items()},
        'best_configs':         all_bests[:20],
        'init_capital_usd':     100.0,
        'fees_bps':             5.0,
        'funding_model':        'directional',
    }
    jp.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n  Saved -> {jp}")
    print("=" * 100)


if __name__ == "__main__":
    main()
