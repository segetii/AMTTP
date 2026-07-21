"""
Ablation study: Energy-Direction Separation (EDS) vs. original eigen-direction
vs. naive momentum.

Validates (empirically) the theorems proven in crypto_eigen_direction_patch.py:

  Theorem 4 predicts the ORIGINAL `compute_crypto_eigen_direction` should show
  a high spurious sign-flip rate (eigenvector sign ambiguity + ill-conditioning),
  and that this should translate into worse/unstable trading performance than
  a sign-continuity + shrinkage corrected version.

  Theorem 3 predicts the EDS combiner (sign(D) * gamma(E)) is well-defined,
  odd, and should not be structurally worse than direction-only, since the
  energy gate only ever scales (never flips) the trade.

Variants tested (all using ONLY causal, already-lagged features -- no
look-ahead: features are z-scored with a rolling window and the resulting
signal is shifted by 1 bar before being multiplied by returns):

  A. naive_momentum   : sign(EWMA of ret_eth over MOM_WIN)
  B. eigen_v1_buggy   : sign(original compute_crypto_eigen_direction)
  C. eigen_v2_fixed   : sign(sign-continuity + shrinkage corrected direction)
  D. eds_full         : eigen_v2_fixed direction * energy-gate confidence

Plus two small sensitivity ablations on variant C/D (window, shrinkage) to
show the fix is not fragile to hyperparameters.
"""
from __future__ import annotations
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
if r"C:\amttp" not in sys.path:
    sys.path.insert(0, r"C:\amttp")

from crypto_eigen_direction_patch import (
    compute_crypto_eigen_direction,
    compute_crypto_eigen_direction_v2,
    compute_energy_gate,
)

DATA_PATH = Path(r"C:\amttp\data\processed\unified_crypto_1h_20210101_to_20260601.parquet")
FEATS = ["ret_eth_z", "vol_eth_z", "btc_dom_z", "cross_disp_z"]
MOM_WIN = 7 * 24          # 7-day naive momentum window (hours)
ANN = np.sqrt(24 * 365)   # hourly annualization factor
TC_BPS = 5.0              # round-trip cost per unit turnover (bps)


def load_data() -> pd.DataFrame:
    df = pd.read_parquet(DATA_PATH)
    return df


def naive_momentum_signal(df: pd.DataFrame) -> pd.Series:
    r = df["ret_eth"].fillna(0)
    mom = r.rolling(MOM_WIN, min_periods=24).sum().shift(1)
    return np.sign(mom).fillna(0.0).rename("naive_momentum")


def sign_flip_rate(signal: pd.Series) -> float:
    """Fraction of consecutive nonzero-to-nonzero transitions where sign flips.
    Measures spurious instability (Theorem 4 diagnostic)."""
    s = signal.values
    prev = s[:-1]
    cur = s[1:]
    mask = (prev != 0) & (cur != 0)
    if mask.sum() == 0:
        return 0.0
    flips = (np.sign(prev[mask]) != np.sign(cur[mask])).sum()
    return float(flips) / float(mask.sum())


def backtest(df: pd.DataFrame, raw_signal: pd.Series, tc_bps: float = TC_BPS) -> dict:
    """Simple, transparent long/short backtest: position = signal shifted by 1
    bar (causal), applied to ret_eth, minus turnover-based transaction costs.
    No vol targeting / no drawdown throttle -- kept deliberately simple so the
    comparison isolates the direction-estimation method itself."""
    pos = raw_signal.shift(1).fillna(0.0)
    ret = df["ret_eth"].fillna(0.0)
    turnover = pos.diff().abs().fillna(0.0)
    gross = pos * ret
    cost = turnover * (tc_bps / 10_000.0)
    net = gross - cost
    equity = (1.0 + net).cumprod() * 100_000.0

    n = len(net)
    ann_ret = net.mean() * 24 * 365
    ann_vol = net.std() * ANN
    sharpe = ann_ret / ann_vol if ann_vol > 1e-12 else 0.0
    years = n / (24 * 365)
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1 if years > 0 else np.nan
    roll_max = equity.cummax()
    dd = equity / roll_max - 1.0
    maxdd = dd.min()
    calmar = cagr / abs(maxdd) if maxdd < 0 else np.nan

    return dict(
        final=float(equity.iloc[-1]),
        sharpe=float(sharpe),
        cagr=float(cagr),
        maxdd=float(maxdd),
        calmar=float(calmar),
        avg_turnover=float(turnover.mean()),
        nan_count=int(raw_signal.isna().sum()),
        flip_rate=float(sign_flip_rate(np.sign(raw_signal.fillna(0.0)))),
    )


def print_table(rows: list[dict], title: str):
    print(f"\n=== {title} ===")
    hdr = f"{'variant':<20}{'final $':>14}{'sharpe':>9}{'cagr':>9}{'maxdd':>9}{'calmar':>9}{'turnover':>10}{'nan':>8}{'flip_rate':>11}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(
            f"{r['variant']:<20}{r['final']:>14,.0f}{r['sharpe']:>9.3f}{r['cagr']*100:>8.2f}%"
            f"{r['maxdd']*100:>8.2f}%{r['calmar']:>9.3f}{r['avg_turnover']:>10.4f}"
            f"{r['nan_count']:>8d}{r['flip_rate']:>11.3f}"
        )


def main():
    df = load_data()
    print(f"Loaded {len(df)} rows, {df.index[0]} -> {df.index[-1]}")

    results = []

    # A. naive momentum baseline
    sig_a = naive_momentum_signal(df)
    m = backtest(df, sig_a)
    m["variant"] = "A_naive_momentum"
    results.append(m)

    # B. original eigen-direction (buggy: sign-ambiguous, no shrinkage)
    d_b = compute_crypto_eigen_direction(df, FEATS, window=60, ret_idx=0)
    sig_b = np.sign(d_b.fillna(0.0)).rename("eigen_v1_buggy")
    m = backtest(df, sig_b)
    m["variant"] = "B_eigen_v1_buggy"
    results.append(m)

    # C. fixed eigen-direction (sign-continuity + shrinkage, Theorem 4 fix)
    d_c = compute_crypto_eigen_direction_v2(df, FEATS, window=60, ret_idx=0, shrinkage=0.15)
    sig_c = np.sign(d_c.fillna(0.0)).rename("eigen_v2_fixed")
    m = backtest(df, sig_c)
    m["variant"] = "C_eigen_v2_fixed"
    results.append(m)

    # D. full EDS: fixed direction * energy confidence gate (Theorem 3)
    _, gate = compute_energy_gate(df, FEATS, window=60, shrinkage=0.15)
    sig_d = (np.sign(d_c.fillna(0.0)) * gate).rename("eds_full")
    m = backtest(df, sig_d)
    m["variant"] = "D_eds_full"
    results.append(m)

    print_table(results, "Main comparison: naive vs buggy-eigen vs fixed-eigen vs full-EDS")

    # --- Sensitivity ablation 1: window size (variant C, direction-only) ---
    win_rows = []
    for win in (40, 60, 90):
        d = compute_crypto_eigen_direction_v2(df, FEATS, window=win, ret_idx=0, shrinkage=0.15)
        s = np.sign(d.fillna(0.0)).rename(f"win{win}")
        m = backtest(df, s)
        m["variant"] = f"C_window={win}"
        win_rows.append(m)
    print_table(win_rows, "Ablation: window-size sensitivity (fixed eigen-direction)")

    # --- Sensitivity ablation 2: shrinkage strength (variant C, direction-only) ---
    shr_rows = []
    for shr in (0.05, 0.15, 0.30):
        d = compute_crypto_eigen_direction_v2(df, FEATS, window=60, ret_idx=0, shrinkage=shr)
        s = np.sign(d.fillna(0.0)).rename(f"shr{shr}")
        m = backtest(df, s)
        m["variant"] = f"C_shrinkage={shr}"
        shr_rows.append(m)
    print_table(shr_rows, "Ablation: shrinkage-strength sensitivity (fixed eigen-direction)")


if __name__ == "__main__":
    main()
