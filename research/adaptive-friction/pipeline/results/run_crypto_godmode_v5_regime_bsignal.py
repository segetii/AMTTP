"""
Crypto Godmode v5 — Regime-Aware b(t) Fix
==========================================

v4 proved train-only price ML and generic feature engineering do NOT beat the
original 7d momentum b(t). This script tests the actual structural fix:
regime-aware b(t), not parameter tuning.

Hypothesis:
  - In broad crypto bull regimes, do not fight beta: use long-biased b(t).
  - Outside bull regimes, use the v1 7d momentum target.
  - Canonical engine remains frozen at v1 champion.

Signals are causal and close-only:
  macro_bull = avg(tanh(30d mom), tanh(90d mom)) across BTC/ETH/SOL, shifted.
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

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')

from run_crypto_canonical_v4 import _stats, print_yoy_table
from run_crypto_canonical_v58_v60 import print_dollar_simulation, run_canonical_sweep as _run_v4_sweep, overlay_v60
from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START, TRAIN_START, build_1h_df
from run_crypto_godmode_v2 import (
    W_TARGET, W_BOX_V1, KAPPA_A, CONV_MIN_V1, ANNEAL_PEAK_V1,
    build_w_star_7d, build_b_aligned, calibrate, run_v2_sweep,
    print_alignment_check, print_strategy_table, print_flag_diagnostics,
)

OUT_DIR_ = Path(OUT_DIR)
BPD = 24
ASSETS = ['btc', 'eth', 'sol']


def _mom(df: pd.DataFrame, asset: str, days: int) -> pd.Series:
    r = df[f'ret_{asset}'].fillna(0.0)
    win = days * BPD
    m = r.rolling(win, min_periods=max(BPD, win // 3)).sum().shift(1).fillna(0.0)
    sd = m.rolling(min(2 * win, len(r)), min_periods=max(BPD, win // 2)).std().replace(0, np.nan)
    return (m / sd).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def macro_bull_score(df: pd.DataFrame) -> np.ndarray:
    scores = []
    for a in ASSETS:
        scores.append(0.65 * np.tanh(_mom(df, a, 30)) + 0.35 * np.tanh(_mom(df, a, 90)))
    s = np.mean(np.column_stack(scores), axis=1)
    return np.clip(s, -1.0, 1.0)


def build_regime_wstars(df: pd.DataFrame, w_v1: np.ndarray) -> dict[str, np.ndarray]:
    bull = macro_bull_score(df)
    bull01_soft = np.clip((bull + 0.20) / 0.70, 0.0, 1.0)  # bull > -0.2 starts long bias
    bull_hard = (bull > 0.0).astype(float)
    strong_bull = (bull > 0.35).astype(float)

    long_all = np.ones_like(w_v1) * W_TARGET
    long_half = np.ones_like(w_v1) * (0.50 * W_TARGET)

    # 1) Soft blend: broad bull -> long beta; otherwise v1 momentum.
    w_soft = (1.0 - bull01_soft[:, None]) * w_v1 + bull01_soft[:, None] * long_all

    # 2) Hard switch: if macro bull, long all assets; if not, v1.
    w_hard = (1.0 - bull_hard[:, None]) * w_v1 + bull_hard[:, None] * long_all

    # 3) No shorts in bull: preserve v1 longs, zero v1 shorts, plus small beta.
    w_noshort = w_v1.copy()
    bull_mask = bull_hard > 0
    w_noshort[bull_mask] = np.maximum(w_noshort[bull_mask], 0.0) + 0.15
    w_noshort = np.clip(w_noshort, -W_TARGET, W_TARGET)

    # 4) Long beta only in strong bull; v1 otherwise.
    w_strong = (1.0 - strong_bull[:, None]) * w_v1 + strong_bull[:, None] * long_all

    # 5) Add beta overlay rather than replace: w = v1 + beta when bull, clipped.
    w_overlay = np.clip(w_v1 + (bull01_soft[:, None] * long_half), -W_TARGET, W_TARGET)

    # 6) Bear protection: if macro deeply negative, halve all exposure.
    bear_cut = np.where(bull < -0.45, 0.50, 1.0)
    w_bearcut = w_v1 * bear_cut[:, None]

    return {
        'v1_ref': w_v1,
        'b_regime_soft': w_soft,
        'b_regime_hard': w_hard,
        'b_noshort_bull': w_noshort,
        'b_strong_bull': w_strong,
        'b_beta_overlay': w_overlay,
        'b_bear_cut': w_bearcut,
    }


def main():
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    SEP = '=' * 100
    print(SEP)
    print('  CRYPTO GODMODE v5 — Regime-Aware b(t) Fix')
    print('  Frozen v1 engine; b(t) becomes macro-regime aware.')
    print(SEP)

    print('\n[1] Fetching Binance data ...')
    df, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_mask = np.asarray(df.index >= TEST_START)
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    print(f'  Bars={len(df):,}  Train={train_mask.sum():,}  Test={test_mask.sum():,}  SOL={has_sol}')

    print('\n[2] Building regime-aware b(t) targets ...')
    w_v1 = build_w_star_7d(df, W_TARGET=W_TARGET)
    wstars = build_regime_wstars(df, w_v1)
    bull = macro_bull_score(df)
    print(f"  macro_bull test: mean={bull[test_mask].mean():+.3f}  "
          f"pct>0={100*(bull[test_mask]>0).mean():.1f}%  pct>0.35={100*(bull[test_mask]>0.35).mean():.1f}%")
    for name, w in wstars.items():
        print(f"  {name:<16} range=[{w.min():+.3f},{w.max():+.3f}] mean_abs={np.mean(np.abs(w)):.3f}")

    print('\n[3] Calibrating and sweeping ...')
    logs = {}
    diags = {}
    for name, w in wstars.items():
        print(f"\n  -- {name} --")
        b = build_b_aligned(w)
        Sigma_f, theta, E_med, diag = calibrate(df, train_mask, w, b, kappa=KAPPA_A, label=name)
        diags[name] = diag
        logs[name] = run_v2_sweep(
            df, train_mask, test_mask, w, b, Sigma_f, theta, E_med,
            sigma_schedule=None, kappa=KAPPA_A, W_box=W_BOX_V1,
            anneal=True, anneal_peak=ANNEAL_PEAK_V1,
            use_flags=False, conv_min=CONV_MIN_V1, adapt_kappa=False,
            label=name)

    print('\n[4] Baselines ...')
    log_base, _ = _run_v4_sweep(df, train_mask, test_mask)
    pnl_v60 = overlay_v60(log_base, train_mask)
    pnl_long = log_base['pnl_long_only']

    strategies = {name: lg['pnl'] for name, lg in logs.items()}
    strategies['v60'] = pnl_v60
    strategies['long_only'] = pnl_long

    print(f"\n{'═'*100}")
    print('  GODMODE V5 REGIME b(t) PERFORMANCE (test 2023→2026, 1× gross, $100 start)')
    print(f"{'═'*100}")
    print_strategy_table(strategies, test_mask)
    print_alignment_check(logs, test_mask)
    print_flag_diagnostics(logs, test_mask)

    print(f"\n  {'─'*80}")
    print('  DELTA vs v1_ref')
    print(f"  {'─'*80}")
    base = _stats(strategies['v1_ref'].iloc[test_mask])
    for name, pnl in strategies.items():
        if name in ('v1_ref', 'v60', 'long_only'):
            continue
        st = _stats(pnl.iloc[test_mask])
        print(f"  {name:<16} dSharpe={st['sharpe']-base['sharpe']:+.3f}  "
              f"dCAGR={(st['cagr']-base['cagr'])*100:+.1f}%  "
              f"dMaxDD={(st['max_dd']-base['max_dd'])*100:+.1f}%  $100→${st['final']:.2f}")

    K_LIST = [1, 2, 3, 5]
    for name, pnl in strategies.items():
        print_yoy_table(name, pnl.iloc[test_mask], K_LIST)

    print(f"\n\n{'▓'*110}")
    print('  $1,000 DOLLAR SIMULATION — regime b(t) variants')
    print(f"{'▓'*110}")
    print_dollar_simulation(strategies, test_mask, start_capital=1000.0, K_list=K_LIST)

    out = {
        'meta': {'version': 'godmode_v5_regime_bsignal', 'rule': 'frozen v1 engine; regime-aware b(t)'},
        'calibration': diags,
        'performance': {n: _stats(p.iloc[test_mask]) for n, p in strategies.items()},
    }
    out_path = OUT_DIR_ / 'crypto_godmode_v5_regime_bsignal.json'
    with open(out_path, 'w') as fh:
        json.dump(out, fh, indent=2, default=float)
    print(f"\n  Saved → {out_path}")
    print(SEP)


if __name__ == '__main__':
    main()
