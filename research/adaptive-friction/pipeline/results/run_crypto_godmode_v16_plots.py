"""
Crypto Godmode v16 — Plots for Selected Champion
================================================

Produces plots requested by the user:

  1. Net equity curves for K=6.0 and K=6.5 under realistic 6 bps round-trip cost.
  2. Drawdown curves for K=6.0 and K=6.5.
  3. Canonical engine 2D state plot: w_BTC vs w_ETH, with target overlay.
  4. Canonical engine 3D state plot: w_BTC, w_ETH, w_SOL trajectory.

Outputs are saved under:
    C:/amttp/research/adaptive-friction/pipeline/results/plots/
"""
from __future__ import annotations

import os
import sys
import json
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, r"C:\amttp\research\adaptive-friction")

from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START, TRAIN_START, build_1h_df
from run_crypto_godmode_v1 import KAPPA_A, W_TARGET_A1, build_w_star, build_b_aligned, calibrate, run_godmode_sweep
from simulate_master_strategy import DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR, simulate_combined, equity_metrics
from simulate_v63_quadrant import CB_HALT, CB_RESUME, CB_WINDOW_DAYS
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from run_crypto_godmode_v8_multiasset_shell import ASSETS, fetch_futures_ohlcv_symbol, build_asset_inputs
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
import run_crypto_godmode_v12_filter_innovate as v12


OUT_DIR_ = Path(OUT_DIR)
PLOT_DIR = OUT_DIR_ / "plots"
BAR = "=" * 112
K_LIST = [6.0, 6.5]
REALISTIC_RT_BPS = 6.0


def replay_unit(unit: pd.Series, k: float) -> dict:
    zero = pd.Series(np.zeros(len(unit)), index=unit.index)
    return simulate_combined(
        unit, zero,
        K_normal=k, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=CB_HALT, cb_resume=CB_RESUME,
        cb_window_days=CB_WINDOW_DAYS, use_cb=True,
    )


def save_equity_plot(equities: dict[float, pd.Series], metrics: dict[float, dict]) -> Path:
    fig, ax = plt.subplots(figsize=(14, 8))
    for k, eq in equities.items():
        label = (f"K={k:.1f}  final=${metrics[k]['final']:,.0f}  "
                 f"MaxDD={metrics[k]['maxdd']:.1%}")
        ax.plot(eq.index, eq.values, linewidth=2.0, label=label)
    ax.set_title("Godmode v16 Net Equity Curve — be50_btc_sol, realistic 6 bps RT", fontsize=15)
    ax.set_ylabel("Equity ($), start = $1,000")
    ax.set_xlabel("Date")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left")
    ax.set_yscale("log")
    fig.tight_layout()
    out = PLOT_DIR / "godmode_v16_equity_k6_k65_net6bps.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def save_drawdown_plot(equities: dict[float, pd.Series]) -> Path:
    fig, ax = plt.subplots(figsize=(14, 6))
    for k, eq in equities.items():
        dd = eq / eq.cummax() - 1.0
        ax.plot(dd.index, 100.0 * dd.values, linewidth=1.8, label=f"K={k:.1f}")
    ax.axhline(-30, color="red", linestyle="--", linewidth=1.0, alpha=0.65, label="-30% DD budget")
    ax.set_title("Godmode v16 Drawdown — K=6.0 vs K=6.5, realistic 6 bps RT", fontsize=15)
    ax.set_ylabel("Drawdown (%)")
    ax.set_xlabel("Date")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="lower left")
    fig.tight_layout()
    out = PLOT_DIR / "godmode_v16_drawdown_k6_k65_net6bps.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def _downsample_idx(n: int, max_points: int = 5000) -> np.ndarray:
    if n <= max_points:
        return np.arange(n)
    return np.linspace(0, n - 1, max_points).astype(int)


def save_canonical_2d(log_ann: pd.DataFrame, w_star: np.ndarray, test_mask: np.ndarray) -> Path:
    s = log_ann.iloc[test_mask].copy()
    ws = w_star[test_mask]
    idx = _downsample_idx(len(s), 4500)
    t = np.linspace(0, 1, len(idx))

    fig, ax = plt.subplots(figsize=(10, 9))
    ax.scatter(ws[idx, 0], ws[idx, 1], s=8, c="orange", alpha=0.20, label="target w* BTC/ETH")
    sc = ax.scatter(s["w_btc"].values[idx], s["w_eth"].values[idx], s=9, c=t,
                    cmap="viridis", alpha=0.75, label="actual canonical w")
    ax.plot(s["w_btc"].values[idx], s["w_eth"].values[idx], color="steelblue", alpha=0.18, linewidth=0.7)
    ax.axhline(0, color="black", linewidth=0.6, alpha=0.5)
    ax.axvline(0, color="black", linewidth=0.6, alpha=0.5)
    ax.set_title("Canonical Engine 2D State Space — BTC weight vs ETH weight", fontsize=14)
    ax.set_xlabel("w_BTC")
    ax.set_ylabel("w_ETH")
    ax.grid(True, alpha=0.22)
    ax.legend(loc="best")
    cbar = fig.colorbar(sc, ax=ax, shrink=0.82)
    cbar.set_label("Time through OOS window")
    fig.tight_layout()
    out = PLOT_DIR / "godmode_v16_canonical_2d_wbtc_weth.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def save_canonical_3d(log_ann: pd.DataFrame, w_star: np.ndarray, test_mask: np.ndarray) -> Path:
    s = log_ann.iloc[test_mask].copy()
    ws = w_star[test_mask]
    idx = _downsample_idx(len(s), 3500)
    c = np.linspace(0, 1, len(idx))

    fig = plt.figure(figsize=(12, 10))
    ax = fig.add_subplot(111, projection="3d")
    ax.scatter(ws[idx, 0], ws[idx, 1], ws[idx, 2], s=5, c="orange", alpha=0.12, label="target w*")
    sc = ax.scatter(s["w_btc"].values[idx], s["w_eth"].values[idx], s["w_sol"].values[idx],
                    s=8, c=c, cmap="viridis", alpha=0.78, label="actual canonical w")
    ax.plot(s["w_btc"].values[idx], s["w_eth"].values[idx], s["w_sol"].values[idx],
            color="steelblue", alpha=0.22, linewidth=0.8)
    ax.set_title("Canonical Engine 3D State Space — BTC / ETH / SOL weights", fontsize=14)
    ax.set_xlabel("w_BTC")
    ax.set_ylabel("w_ETH")
    ax.set_zlabel("w_SOL")
    ax.legend(loc="upper left")
    cbar = fig.colorbar(sc, ax=ax, shrink=0.65, pad=0.10)
    cbar.set_label("Time through OOS window")
    fig.tight_layout()
    out = PLOT_DIR / "godmode_v16_canonical_3d_weights.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def save_canonical_dashboard(log_ann: pd.DataFrame, test_mask: np.ndarray) -> Path:
    s = log_ann.iloc[test_mask].copy()
    fig, axes = plt.subplots(4, 1, figsize=(14, 11), sharex=True)
    axes[0].plot(s.index, s["E"], color="purple", linewidth=1.0)
    axes[0].set_ylabel("Energy E")
    axes[0].set_title("Canonical Cockpit Scalars — OOS")
    axes[1].plot(s.index, s["gamma"], color="firebrick", linewidth=1.0)
    axes[1].set_ylabel("gamma")
    axes[2].plot(s.index, s["cos_theta"], color="teal", linewidth=1.0)
    axes[2].axhline(0, color="black", linewidth=0.8, alpha=0.6)
    axes[2].set_ylabel("cos(theta)")
    axes[3].plot(s.index, s["w_btc"], label="BTC", linewidth=1.0)
    axes[3].plot(s.index, s["w_eth"], label="ETH", linewidth=1.0)
    axes[3].plot(s.index, s["w_sol"], label="SOL", linewidth=1.0)
    axes[3].set_ylabel("weights")
    axes[3].legend(loc="upper left", ncol=3)
    for ax in axes:
        ax.grid(True, alpha=0.22)
    fig.tight_layout()
    out = PLOT_DIR / "godmode_v16_canonical_cockpit.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def main():
    t0 = time.time()
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    print(BAR)
    print("  CRYPTO GODMODE v16 — PLOTS")
    print(BAR)

    print("\n[1] Rebuilding canonical signal and v12 champion unit book ...")
    df, has_sol = build_1h_df(start="2021-01-01", end="2026-05-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask = np.asarray(df.index >= TEST_START)
    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()
    w_star = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    Sigma_f, theta, diag = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label="v16")
    log_ann = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned, Sigma_f, theta,
                                kappa=KAPPA_A, anneal=True, label="v16_anneal")
    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=False)
    inputs_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=True)
    inputs = attach_q_hot(inputs_noq, inputs_q)
    sig_map = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}") for asset, _, _, idx in ASSETS}
    cfg = next(c for c in v12.VARIANTS if c["name"] == "be50_btc_sol")
    v12.RT_COST = REALISTIC_RT_BPS / 10_000.0
    unit_res = v12.run_variant(cfg, inputs, sig_map, log_ann)

    print("\n[2] Replaying K=6.0 and K=6.5 with realistic 6 bps RT ...")
    equities = {}
    metrics = {}
    test_ts = pd.Timestamp(TEST_START)
    for k in K_LIST:
        res = replay_unit(unit_res["unit"], k)
        eq_oos = res["eq"][res["eq"].index >= test_ts]
        equities[k] = eq_oos
        metrics[k] = equity_metrics(eq_oos, f"K{k}")
        print(f"  K={k:.1f}: final=${metrics[k]['final']:,.2f} maxdd={metrics[k]['maxdd']:+.2%} sharpe={metrics[k]['sharpe']:+.3f}")

    print("\n[3] Saving plots ...")
    paths = []
    paths.append(save_equity_plot(equities, metrics))
    paths.append(save_drawdown_plot(equities))
    paths.append(save_canonical_2d(log_ann, w_star, test_mask))
    paths.append(save_canonical_3d(log_ann, w_star, test_mask))
    paths.append(save_canonical_dashboard(log_ann, test_mask))
    for p in paths:
        print(f"  saved: {p}")

    payload = dict(
        meta=dict(version="godmode_v16_plots", rt_bps=REALISTIC_RT_BPS, k_list=K_LIST,
                  theta=diag["theta"], elapsed=time.time() - t0),
        metrics=metrics,
        plots=[str(p) for p in paths],
    )
    out = OUT_DIR_ / "crypto_godmode_v16_plots.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=float)
    print(f"\n  Saved manifest → {out}")
    print(f"  elapsed={time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()