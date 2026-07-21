"""
Crypto Godmode v4 — Fix b(t), Not the Canonical Engine
=======================================================

v2/v3 showed the engine mechanics should remain frozen at the v1 champion:
  κ=0.15, W_BOX=0.50, CONV_MIN=0.20, ANNEAL_PEAK=12, fixed Sigma.

This script fixes the real bottleneck: b(t).

Canonical mapping is unchanged:
  w_star(t) = predictive weight-space target
  b(t)      = A @ w_star(t)
  S(w,t)   = Aw - b(t)

Tested b(t) variants:
  v1_ref       — old 7d realized momentum target
  b_trendmix   — causal multi-horizon trend stack without 1d noise over-weighting
  b_breakout   — causal Donchian/range breakout target
  b_xsection   — causal cross-sectional relative-strength target
  b_ml6        — train-only Ridge model predicting next 6h normalized return
  b_ml24       — train-only Ridge model predicting next 24h normalized return
  b_ml72       — train-only Ridge model predicting next 72h normalized return
  b_ml_ens     — average of ml6/ml24/ml72
  b_hybrid     — blend of v1_ref + ml_ens + breakout

No engine changes. Only b(t) changes.
"""
from __future__ import annotations
import os, sys, json, time, warnings
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

from run_crypto_canonical_v4 import A_FACTORS, _stats, print_yoy_table
from run_crypto_canonical_v58_v60 import (
    print_dollar_simulation, run_canonical_sweep as _run_v4_sweep, overlay_v60,
)
from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START, TRAIN_START, build_1h_df
from run_crypto_godmode_v2 import (
    W_TARGET, W_BOX_V1, KAPPA_A, CONV_MIN_V1, ANNEAL_PEAK_V1,
    build_w_star_7d, build_b_aligned, calibrate, run_v2_sweep,
    print_alignment_check, print_strategy_table, print_flag_diagnostics,
)

OUT_DIR_ = Path(OUT_DIR)
BPD = 24
ASSETS = ['btc', 'eth', 'sol']


# ═══════════════════════════════════════════════════════════════════════════
#  CAUSAL FEATURE HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _zscore(s: pd.Series, win: int, minp: int | None = None) -> pd.Series:
    if minp is None:
        minp = max(24, win // 4)
    mu = s.rolling(win, min_periods=minp).mean()
    sd = s.rolling(win, min_periods=minp).std().replace(0, np.nan)
    return ((s - mu) / sd).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _safe_tanh(x: pd.Series | np.ndarray, scale: float = 1.0) -> np.ndarray:
    arr = np.asarray(x, dtype=float)
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    return np.tanh(scale * arr)


def _ret(df: pd.DataFrame, a: str) -> pd.Series:
    return df[f'ret_{a}'].fillna(0.0)


def _price(df: pd.DataFrame, a: str) -> pd.Series:
    return df[a].astype(float)


def _roll_sum_shifted(r: pd.Series, win: int) -> pd.Series:
    minp = min(win, max(2, min(win, BPD)))
    return r.rolling(win, min_periods=minp).sum().shift(1).fillna(0.0)


def _mom_z(r: pd.Series, win: int) -> pd.Series:
    m = _roll_sum_shifted(r, win)
    sd_win = min(2 * win, len(r))
    minp = min(sd_win, max(2, min(24, win // 2 if win >= 4 else win)))
    sd = m.rolling(sd_win, min_periods=minp).std().replace(0, np.nan)
    return (m / sd).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _normalize_wstar(w: np.ndarray, target: float = W_TARGET) -> np.ndarray:
    """Clip per asset and preserve shape."""
    return np.clip(np.nan_to_num(w, nan=0.0, posinf=0.0, neginf=0.0), -target, target)


# ═══════════════════════════════════════════════════════════════════════════
#  HAND-BUILT b(t) SIGNALS
# ═══════════════════════════════════════════════════════════════════════════

def build_w_star_trendmix(df: pd.DataFrame, target: float = W_TARGET) -> np.ndarray:
    """Causal trend stack: 12h + 3d + 7d + 21d.

    Unlike v2's failed multiwin, this reduces 1d noise and emphasizes persistent
    3d/7d/21d agreement.
    """
    cols = []
    for a in ASSETS:
        r = _ret(df, a)
        s = (0.15 * _safe_tanh(_mom_z(r, 12), 0.75)
             + 0.35 * _safe_tanh(_mom_z(r, 3 * BPD), 1.00)
             + 0.35 * _safe_tanh(_mom_z(r, 7 * BPD), 1.00)
             + 0.15 * _safe_tanh(_mom_z(r, 21 * BPD), 1.00))
        cols.append(s)
    return _normalize_wstar(np.column_stack(cols) * target, target)


def build_w_star_breakout(df: pd.DataFrame, target: float = W_TARGET) -> np.ndarray:
    """Causal Donchian/range breakout target.

    Uses prior 20d and 60d high/low ranges. Positive near prior high breakout,
    negative near prior low breakdown. No current-bar lookahead: high/low from
    close-only history are shifted by one bar.
    """
    cols = []
    for a in ASSETS:
        p = _price(df, a)
        p_lag = p.shift(1)
        hi20 = p.shift(1).rolling(20 * BPD, min_periods=7 * BPD).max()
        lo20 = p.shift(1).rolling(20 * BPD, min_periods=7 * BPD).min()
        hi60 = p.shift(1).rolling(60 * BPD, min_periods=20 * BPD).max()
        lo60 = p.shift(1).rolling(60 * BPD, min_periods=20 * BPD).min()
        pos20 = ((p_lag - lo20) / (hi20 - lo20).replace(0, np.nan) - 0.5) * 2.0
        pos60 = ((p_lag - lo60) / (hi60 - lo60).replace(0, np.nan) - 0.5) * 2.0
        # Add 7d momentum confirmation to avoid buying stale highs blindly.
        mom7 = _safe_tanh(_mom_z(_ret(df, a), 7 * BPD), 1.0)
        sig = 0.45 * _safe_tanh(pos20, 1.5) + 0.35 * _safe_tanh(pos60, 1.25) + 0.20 * mom7
        cols.append(sig)
    return _normalize_wstar(np.column_stack(cols) * target, target)


def build_w_star_xsection(df: pd.DataFrame, target: float = W_TARGET) -> np.ndarray:
    """Cross-sectional relative strength with small market beta.

    Keeps the best asset overweight and weakest underweight. Adds a market trend
    component so the engine can still go net-long in broad bull phases.
    """
    moms = []
    for a in ASSETS:
        r = _ret(df, a)
        moms.append(0.55 * _mom_z(r, 7 * BPD) + 0.45 * _mom_z(r, 21 * BPD))
    M = pd.DataFrame(np.column_stack(moms), index=df.index, columns=ASSETS).fillna(0.0)
    rel = M.sub(M.median(axis=1), axis=0)
    market = M.mean(axis=1)
    sig = 0.65 * np.tanh(rel.values) + 0.35 * np.tanh(market.values[:, None])
    return _normalize_wstar(sig * target, target)


# ═══════════════════════════════════════════════════════════════════════════
#  TRAIN-ONLY RIDGE PREDICTIVE b(t)
# ═══════════════════════════════════════════════════════════════════════════

def build_feature_matrix(df: pd.DataFrame, asset: str) -> pd.DataFrame:
    """Causal feature matrix for one asset. All features use t-1 or older data."""
    r = _ret(df, asset)
    p = _price(df, asset)
    feats = {}

    # Own momentum stack.
    for h in [3, 6, 12, 24, 3 * BPD, 7 * BPD, 14 * BPD, 30 * BPD]:
        feats[f'{asset}_mom_{h}'] = _mom_z(r, h)

    # Volatility state and vol compression/expansion.
    rv1 = r.rolling(BPD, min_periods=12).std().shift(1)
    rv7 = r.rolling(7 * BPD, min_periods=3 * BPD).std().shift(1)
    rv30 = r.rolling(30 * BPD, min_periods=10 * BPD).std().shift(1)
    feats[f'{asset}_rv1_z'] = _zscore(rv1.fillna(0.0), 30 * BPD)
    feats[f'{asset}_rv7_z'] = _zscore(rv7.fillna(0.0), 60 * BPD)
    feats[f'{asset}_vol_ratio'] = ((rv7 / rv30.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(1.0) - 1.0)

    # Range position / breakout state.
    for d in [20, 60]:
        hi = p.shift(1).rolling(d * BPD, min_periods=max(7 * BPD, d * BPD // 3)).max()
        lo = p.shift(1).rolling(d * BPD, min_periods=max(7 * BPD, d * BPD // 3)).min()
        feats[f'{asset}_range_{d}d'] = ((p.shift(1) - lo) / (hi - lo).replace(0, np.nan) - 0.5).fillna(0.0)

    # Cross asset/macro crypto structure.
    for other in ASSETS:
        ro = _ret(df, other)
        feats[f'{other}_mom7'] = _mom_z(ro, 7 * BPD)
        feats[f'{asset}_minus_{other}_mom7'] = _mom_z(r - ro, 7 * BPD)

    feats['btc_dom_mom7'] = _mom_z(df['btc_dom'].fillna(0.0), 7 * BPD)
    feats['eth_btc_spread_mom7'] = _mom_z(df['spread_ret_eb'].fillna(0.0), 7 * BPD)

    # Time-of-day seasonality (crypto liquidity cycle), known at t.
    hour = df.index.hour.astype(float)
    feats['hour_sin'] = np.sin(2.0 * np.pi * hour / 24.0)
    feats['hour_cos'] = np.cos(2.0 * np.pi * hour / 24.0)

    X = pd.DataFrame(feats, index=df.index)
    X = X.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    # Robust squashing to prevent one feature dominating.
    for c in X.columns:
        if c not in ('hour_sin', 'hour_cos'):
            X[c] = np.clip(X[c], -6.0, 6.0)
    return X


def build_w_star_ml(df: pd.DataFrame, train_mask: np.ndarray, horizon: int, target: float = W_TARGET) -> np.ndarray:
    """Train-only Ridge model predicts future horizon normalized return.

    For each asset:
      y_t = sum_{t+1:t+horizon} ret / realized_vol_7d
    Fit only on train_mask bars where y is known. Predict all bars causally.
    """
    from sklearn.linear_model import RidgeCV
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline

    preds = []
    for a in ASSETS:
        X = build_feature_matrix(df, a)
        r = _ret(df, a)
        fut = r.shift(-1).rolling(horizon, min_periods=horizon).sum().shift(-(horizon - 1))
        vol = r.rolling(7 * BPD, min_periods=3 * BPD).std().shift(1).replace(0, np.nan)
        y = (fut / (vol * np.sqrt(horizon) + 1e-9)).replace([np.inf, -np.inf], np.nan)

        valid = train_mask & np.isfinite(y.values)
        if valid.sum() < 1000:
            raise RuntimeError(f'Not enough training rows for {a} horizon={horizon}: {valid.sum()}')

        model = make_pipeline(
            StandardScaler(),
            RidgeCV(alphas=np.logspace(-3, 3, 13))
        )
        model.fit(X.iloc[valid].values, y.iloc[valid].values)
        pred = model.predict(X.values)

        # Calibrate prediction scale on train only; squash to target.
        pred_s = pd.Series(pred, index=df.index)
        train_std = float(pred_s.iloc[train_mask].std())
        if not np.isfinite(train_std) or train_std <= 1e-9:
            train_std = 1.0
        sig = np.tanh(pred_s / (1.25 * train_std)).values
        preds.append(sig)

        ridge = model.named_steps['ridgecv']
        print(f"    [ml{horizon:02d}] {a}: alpha={ridge.alpha_:.4g}  pred_train_std={train_std:.4f}")

    return _normalize_wstar(np.column_stack(preds) * target, target)


def blend_wstars(*pairs: tuple[float, np.ndarray], target: float = W_TARGET) -> np.ndarray:
    total = np.zeros_like(pairs[0][1])
    wsum = 0.0
    for weight, arr in pairs:
        total += weight * arr
        wsum += weight
    if wsum <= 0:
        return total
    return _normalize_wstar(total / wsum, target)


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    SEP = '=' * 100
    print(SEP)
    print('  CRYPTO GODMODE v4 — b(t) Signal Fix')
    print('  Engine frozen at v1 champion; only w_star(t) / b(t)=A@w_star(t) changes.')
    print(SEP)

    print('\n[1] Fetching Binance data ...')
    df, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_mask = np.asarray(df.index >= TEST_START)
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    print(f'  Bars={len(df):,}  Train={train_mask.sum():,}  Test={test_mask.sum():,}  SOL={has_sol}')

    print('\n[2] Building candidate w_star(t) signals ...')
    w_v1 = build_w_star_7d(df, W_TARGET=W_TARGET)
    w_trend = build_w_star_trendmix(df)
    w_break = build_w_star_breakout(df)
    w_xsec = build_w_star_xsection(df)

    print('  Training Ridge predictive signals (train only: 2021-2022) ...')
    w_ml6 = build_w_star_ml(df, train_mask, horizon=6)
    w_ml24 = build_w_star_ml(df, train_mask, horizon=24)
    w_ml72 = build_w_star_ml(df, train_mask, horizon=72)
    w_mlens = blend_wstars((1.0, w_ml6), (1.0, w_ml24), (1.0, w_ml72))
    w_hybrid = blend_wstars((0.45, w_v1), (0.35, w_mlens), (0.20, w_break))

    wstars = {
        'v1_ref': w_v1,
        'b_trendmix': w_trend,
        'b_breakout': w_break,
        'b_xsection': w_xsec,
        'b_ml6': w_ml6,
        'b_ml24': w_ml24,
        'b_ml72': w_ml72,
        'b_ml_ens': w_mlens,
        'b_hybrid': w_hybrid,
    }
    for name, w in wstars.items():
        print(f"  {name:<12} range=[{w.min():+.3f},{w.max():+.3f}]  "
              f"mean_abs={np.mean(np.abs(w)):.3f}")

    print('\n[3] Calibrating and sweeping each b(t) ...')
    logs = {}
    diags = {}
    for name, w in wstars.items():
        print(f"\n  -- {name} --")
        b = build_b_aligned(w)
        Sigma_f, theta, E_med, diag = calibrate(df, train_mask, w, b, kappa=KAPPA_A, label=name)
        diags[name] = diag
        logs[name] = run_v2_sweep(
            df, train_mask, test_mask, w, b, Sigma_f, theta, E_med,
            sigma_schedule=None,
            kappa=KAPPA_A,
            W_box=W_BOX_V1,
            anneal=True,
            anneal_peak=ANNEAL_PEAK_V1,
            use_flags=False,
            conv_min=CONV_MIN_V1,
            adapt_kappa=False,
            label=name,
        )

    print('\n[4] Baselines ...')
    log_base, _ = _run_v4_sweep(df, train_mask, test_mask)
    pnl_v60 = overlay_v60(log_base, train_mask)
    pnl_long = log_base['pnl_long_only']

    strategies = {name: lg['pnl'] for name, lg in logs.items()}
    strategies['v60'] = pnl_v60
    strategies['long_only'] = pnl_long

    print(f"\n{'═'*100}")
    print('  GODMODE V4 b(t) SIGNAL PERFORMANCE  (test 2023→2026, 1× gross, $100 start)')
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
        print(f"  {name:<12} dSharpe={st['sharpe']-base['sharpe']:+.3f}  "
              f"dCAGR={(st['cagr']-base['cagr'])*100:+.1f}%  "
              f"dMaxDD={(st['max_dd']-base['max_dd'])*100:+.1f}%  "
              f"$100→${st['final']:.2f}")

    K_LIST = [1, 2, 3, 5]
    for name, pnl in strategies.items():
        print_yoy_table(name, pnl.iloc[test_mask], K_LIST)

    print(f"\n\n{'▓'*110}")
    print('  $1,000 DOLLAR SIMULATION — b(t) variants')
    print(f"{'▓'*110}")
    print_dollar_simulation(strategies, test_mask, start_capital=1000.0, K_list=K_LIST)

    out = {
        'meta': {
            'version': 'godmode_v4_bsignal',
            'core_rule': 'canonical engine frozen; only b(t)=A@w_star(t) changes',
            'W_TARGET': W_TARGET,
            'W_BOX': W_BOX_V1,
            'KAPPA_A': KAPPA_A,
            'CONV_MIN': CONV_MIN_V1,
            'ANNEAL_PEAK': ANNEAL_PEAK_V1,
        },
        'calibration': diags,
        'performance': {n: _stats(p.iloc[test_mask]) for n, p in strategies.items()},
    }
    out_path = OUT_DIR_ / 'crypto_godmode_v4_bsignal.json'
    with open(out_path, 'w') as fh:
        json.dump(out, fh, indent=2, default=float)
    print(f"\n  Saved → {out_path}")
    print(SEP)


if __name__ == '__main__':
    main()
