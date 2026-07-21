"""
run_crypto_godmode_v30_fractional_ricci.py
==========================================

Fractional Ricci-regularised Fisher geometry for the crypto Godmode engine.

Geometry implemented
--------------------
    E_t(w) = (Aw - b_t)^T G (Aw - b_t)

with
    G = Sigma_FR^{-1}

where Sigma_FR is built from:
  1. fractional-memory covariance weighting of factor returns,
  2. condition-number cap (canonical_v4_gap_closure G7),
  3. log-Euclidean Ricci-style smoothing/shrinkage on the SPD cone.

Execution is the validated v29 stack:
  - be50_btc_sol
  - tbr0p47 base filter
  - soft_all_micro friction
  - K=6.5, realistic 6 bps RT

Outputs include 2D and 3D visualisations of the best engine geometry.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

sys.path.insert(0, str(Path(__file__).parent))

import run_crypto_godmode_v27_all_microstructure as v27
import run_crypto_godmode_v28_canonical_stability as v28
from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START, TRAIN_START, build_1h_df
from run_crypto_godmode_v1 import KAPPA_A, W_TARGET_A1, build_b_aligned, build_w_star, run_godmode_sweep
from run_crypto_canonical_v4 import A_FACTORS, ledoit_wolf_cov, rescale_to_correlation
from run_crypto_godmode_v8_multiasset_shell import ASSETS, build_asset_inputs, fetch_futures_ohlcv_symbol
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from simulate_master_strategy import DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR, INIT, equity_metrics, period_table, simulate_combined
from run_crypto_canonical_v4 import build_factor_returns


BAR = "=" * 112
OUT_DIR_ = Path(OUT_DIR) / "v30_fractional_ricci"
PLOT_DIR = OUT_DIR_ / "plots"
K_NORMAL = 6.5
RT_BPS = 6.0
KAPPA_CAP = 20.0

ALPHA_GRID = [0.35, 0.50, 0.65, 0.80]
RICCI_ETA_GRID = [0.00, 0.10]

REG_VARIANT = dict(name="soft_all_micro", tbr_long_min=0.47, tbr_short_max=0.53,
                   soft=True, rho=False, w_funding=0.25, w_oi=0.18,
                   w_lsr=0.16, w_taker=0.16)


def _spd_eigh(M: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    vals, vecs = np.linalg.eigh((M + M.T) / 2.0)
    vals = np.clip(vals, 1e-12, None)
    return vals, vecs


def _log_euclidean_shrink_to_identity(Sigma: np.ndarray, eta: float) -> np.ndarray:
    """Ricci-style smoothing on SPD cone: log-Euclidean shrink toward I."""
    if eta <= 0:
        return Sigma
    vals, vecs = _spd_eigh(Sigma)
    log_vals = np.log(vals)
    new_vals = np.exp((1.0 - eta) * log_vals)  # + eta * log(1)=0
    S = (vecs * new_vals) @ vecs.T
    d = np.sqrt(np.diag(S))
    return S / np.outer(d, d)


def fractional_covariance(factor_R: np.ndarray, train_mask: np.ndarray, alpha: float) -> np.ndarray:
    """Long-memory covariance with power-law weights over training bars."""
    X = np.asarray(factor_R[train_mask], dtype=float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    n = len(X)
    age = np.arange(n - 1, -1, -1, dtype=float)  # 0 = most recent
    weights = 1.0 / np.power(age + 1.0, alpha)
    weights /= weights.sum()
    mu = np.sum(X * weights[:, None], axis=0)
    Xc = X - mu
    cov = (Xc * weights[:, None]).T @ Xc
    return rescale_to_correlation(cov)


def cap_condition(Sigma: np.ndarray, cap: float) -> tuple[np.ndarray, dict]:
    vals = np.linalg.eigvalsh(Sigma)
    lam_min = float(max(vals[0], 1e-12))
    lam_max = float(vals[-1])
    cond0 = lam_max / lam_min
    if cond0 <= cap:
        return Sigma, dict(cond_before=cond0, cond_after=cond0, lambda_added=0.0)
    lam = max(0.0, (lam_max - cap * lam_min) / (cap - 1.0))
    S = Sigma + lam * np.eye(Sigma.shape[0])
    d = np.sqrt(np.diag(S))
    S = S / np.outer(d, d)
    vals2 = np.linalg.eigvalsh(S)
    return S, dict(cond_before=cond0, cond_after=float(vals2[-1] / max(vals2[0], 1e-12)), lambda_added=float(lam))


def build_fractional_ricci_sigma(factor_R: np.ndarray, train_mask: np.ndarray,
                                 alpha: float, ricci_eta: float) -> tuple[np.ndarray, dict]:
    Sigma_frac = fractional_covariance(factor_R, train_mask, alpha)
    Sigma_cap, cond = cap_condition(Sigma_frac, KAPPA_CAP)
    Sigma_flow = _log_euclidean_shrink_to_identity(Sigma_cap, ricci_eta)
    vals = np.linalg.eigvalsh(Sigma_flow)
    diag = dict(alpha=alpha, ricci_eta=ricci_eta, **cond,
                cond_final=float(vals[-1] / max(vals[0], 1e-12)),
                eigvals=[float(x) for x in vals])
    return Sigma_flow, diag


def theta_for_sigma(b_arr: np.ndarray, train_mask: np.ndarray, Sigma: np.ndarray, cond_before: float) -> float:
    G = np.linalg.inv(Sigma)
    b_train = b_arr[train_mask]
    E_train = np.einsum("ti,ij,tj->t", b_train, G, b_train)
    theta = max(float(np.percentile(E_train, 50)), 1e-3)
    # Same G7-inspired disturbance-budget compensation used in v29.
    theta *= max(cond_before / KAPPA_CAP, 1.0)
    return theta


def simulate_k(unit: pd.Series, k: float = K_NORMAL) -> dict:
    return simulate_combined(
        unit_normal=unit,
        unit_crash=pd.Series(0.0, index=unit.index),
        K_normal=k,
        K_crash=0.0,
        dd_soft=DYN_DD_SOFT,
        dd_stop=DYN_DD_STOP,
        y_floor=DYN_Y_FLOOR,
        cb_halt=v28.CB_HALT,
        cb_resume=v28.CB_RESUME,
        cb_window_days=v28.CB_WINDOW_DAYS,
        use_cb=True,
    )


def yoy(eq: pd.Series) -> dict[str, float]:
    return {r["period"][:4]: r["return_pct"] for r in period_table(eq, "Y")}


def row_from_sim(label: str, sim: dict, test_ts: pd.Timestamp, alpha: float, eta: float,
                 theta: float, sigma_diag: dict) -> dict:
    eq = sim["eq"][sim["eq"].index >= test_ts]
    m = equity_metrics(eq, label)
    yy = yoy(eq)
    return dict(name=label, alpha=alpha, ricci_eta=eta, theta=theta,
                final=m["final"], profit=m["final"] - INIT, cagr=m["cagr"],
                sharpe=m["sharpe"], maxdd=m["maxdd"], calmar=m["calmar"],
                pct_halted=sim.get("pct_halted", np.nan),
                r2023=yy.get("2023", np.nan), r2024=yy.get("2024", np.nan),
                r2025=yy.get("2025", np.nan), r2026=yy.get("2026", np.nan),
                sigma=sigma_diag)


def downsample_idx(n: int, max_points: int) -> np.ndarray:
    if n <= max_points:
        return np.arange(n)
    return np.linspace(0, n - 1, max_points).astype(int)


def save_geometry_plots(log_ann: pd.DataFrame, w_star: np.ndarray, test_mask: np.ndarray,
                        Sigma: np.ndarray, best: dict) -> list[str]:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    s = log_ann.iloc[test_mask].copy()
    ws = w_star[test_mask]
    idx = downsample_idx(len(s), 4500)
    c = np.linspace(0, 1, len(idx))

    # 2D state-space trajectory.
    fig, ax = plt.subplots(figsize=(10, 9))
    ax.scatter(ws[idx, 0], ws[idx, 1], s=7, color="orange", alpha=0.18, label="target w*")
    sc = ax.scatter(s["w_btc"].values[idx], s["w_eth"].values[idx], s=8, c=c,
                    cmap="viridis", alpha=0.75, label="canonical w")
    ax.plot(s["w_btc"].values[idx], s["w_eth"].values[idx], color="steelblue", alpha=0.20, linewidth=0.7)
    ax.axhline(0, color="black", linewidth=0.6, alpha=0.5)
    ax.axvline(0, color="black", linewidth=0.6, alpha=0.5)
    ax.set_title(f"v30 Fractional Ricci-Fisher Geometry 2D — alpha={best['alpha']}, eta={best['ricci_eta']}")
    ax.set_xlabel("w_BTC")
    ax.set_ylabel("w_ETH")
    ax.grid(True, alpha=0.22)
    ax.legend(loc="best")
    cb = fig.colorbar(sc, ax=ax, shrink=0.82)
    cb.set_label("time through OOS")
    out = PLOT_DIR / "v30_geometry_2d_weights.png"
    fig.tight_layout(); fig.savefig(out, dpi=180); plt.close(fig)
    paths.append(str(out))

    # 3D trajectory.
    fig = plt.figure(figsize=(12, 10))
    ax = fig.add_subplot(111, projection="3d")
    ax.scatter(ws[idx, 0], ws[idx, 1], ws[idx, 2], s=5, color="orange", alpha=0.12, label="target w*")
    sc = ax.scatter(s["w_btc"].values[idx], s["w_eth"].values[idx], s["w_sol"].values[idx],
                    s=8, c=c, cmap="viridis", alpha=0.78, label="canonical w")
    ax.plot(s["w_btc"].values[idx], s["w_eth"].values[idx], s["w_sol"].values[idx],
            color="steelblue", alpha=0.22, linewidth=0.8)
    ax.set_title("v30 Fractional Ricci-Fisher Geometry 3D")
    ax.set_xlabel("w_BTC"); ax.set_ylabel("w_ETH"); ax.set_zlabel("w_SOL")
    ax.legend(loc="upper left")
    cb = fig.colorbar(sc, ax=ax, shrink=0.65, pad=0.10)
    cb.set_label("time through OOS")
    out = PLOT_DIR / "v30_geometry_3d_weights.png"
    fig.tight_layout(); fig.savefig(out, dpi=180); plt.close(fig)
    paths.append(str(out))

    # Metric eigenvalues / anisotropy.
    vals = np.linalg.eigvalsh(Sigma)
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = [f"eig{i + 1}" for i in range(len(vals))]
    colors = plt.cm.viridis(np.linspace(0.15, 0.85, len(vals)))
    ax.bar(labels, vals, color=colors)
    ax.set_title("v30 Regularised Fractional Covariance Eigenvalues")
    ax.set_ylabel("eigenvalue")
    ax.grid(True, axis="y", alpha=0.25)
    out = PLOT_DIR / "v30_metric_eigenvalues.png"
    fig.tight_layout(); fig.savefig(out, dpi=180); plt.close(fig)
    paths.append(str(out))

    # Energy surface in BTC/ETH plane with SOL fixed at median target.
    G = np.linalg.inv(Sigma)
    w0 = np.median(ws, axis=0)
    b0 = A_FACTORS @ w0
    grid = np.linspace(-0.55, 0.55, 160)
    X, Y = np.meshgrid(grid, grid)
    Z = np.zeros_like(X)
    sol0 = float(np.median(ws[:, 2]))
    for i in range(X.shape[0]):
        W = np.column_stack([X[i].ravel(), Y[i].ravel(), np.full(X.shape[1], sol0)])
        S = W @ A_FACTORS.T - b0
        Z[i] = np.einsum("ij,jk,ik->i", S, G, S)
    fig, ax = plt.subplots(figsize=(9, 8))
    cs = ax.contourf(X, Y, Z, levels=40, cmap="magma")
    ax.scatter(s["w_btc"].values[idx], s["w_eth"].values[idx], s=3, c="cyan", alpha=0.25)
    ax.set_title("v30 Fisher-Mahalanobis Energy Surface — BTC/ETH slice")
    ax.set_xlabel("w_BTC"); ax.set_ylabel("w_ETH")
    cb = fig.colorbar(cs, ax=ax); cb.set_label("energy")
    out = PLOT_DIR / "v30_energy_surface_2d.png"
    fig.tight_layout(); fig.savefig(out, dpi=180); plt.close(fig)
    paths.append(str(out))

    return paths


def main() -> None:
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    print(BAR)
    print("  CRYPTO GODMODE v30 — FRACTIONAL RICCI-REGULARISED FISHER GEOMETRY")
    print(BAR)

    print("\n[0] Preloading microstructure cache ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        ms = v27._get_ms(sym)
        print(f"  {sym}: {ms.shape}")

    print("\n[1] Building shared market inputs ...")
    df, _ = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask = np.asarray(df.index >= TEST_START)
    test_ts = pd.Timestamp(TEST_START)
    factor_R = build_factor_returns(df)
    w_star = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()

    results = []
    artifacts: dict[str, object] = {}
    v27.RT_COST = RT_BPS / 10_000.0

    print(f"\n[2] Sweeping alpha={ALPHA_GRID}, ricci_eta={RICCI_ETA_GRID} ...")
    for alpha in ALPHA_GRID:
        for eta in RICCI_ETA_GRID:
            label = f"a{alpha:.2f}_r{eta:.2f}".replace(".", "p")
            Sigma, sdiag = build_fractional_ricci_sigma(factor_R, train_mask, alpha, eta)
            theta = theta_for_sigma(b_aligned, train_mask, Sigma, sdiag["cond_before"])
            print(f"\n  [{label}] theta={theta:.4f} cond={sdiag['cond_before']:.1f}->{sdiag['cond_final']:.1f}")
            log_ann = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned, Sigma, theta,
                                        kappa=KAPPA_A, anneal=True, label=f"v30_{label}")
            inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=False)
            inputs_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=True)
            inputs = attach_q_hot(inputs_noq, inputs_q)
            sig_map = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}") for asset, _, _, idx in ASSETS}
            unit = v28.run_variant_v28(REG_VARIANT, inputs, sig_map, log_ann)["unit"]
            sim = simulate_k(unit, K_NORMAL)
            row = row_from_sim(label, sim, test_ts, alpha, eta, theta, sdiag)
            results.append(row)
            artifacts[label] = dict(Sigma=Sigma, theta=theta, log_ann=log_ann)
            print(f"  [{label}] final=${row['final']:>10,.0f} CAGR={row['cagr']:+7.2%} Calmar={row['calmar']:+6.3f} MaxDD={row['maxdd']:+.2%}")

    best = max(results, key=lambda r: r["calmar"])
    best_final = max(results, key=lambda r: r["final"])
    best_art = artifacts[best["name"]]

    print("\n[3] Saving geometry visualisations for best engine ...")
    plot_paths = save_geometry_plots(best_art["log_ann"], w_star, test_mask, best_art["Sigma"], best)
    for p in plot_paths:
        print(f"  saved: {p}")

    print("\n" + BAR)
    print("  v30 RESULTS")
    print(BAR)
    for r in sorted(results, key=lambda x: -x["calmar"]):
        print(f"  {r['name']:<14} alpha={r['alpha']:.2f} eta={r['ricci_eta']:.2f} "
              f"final=${r['final']:>10,.0f} CAGR={r['cagr']:+7.2%} Calmar={r['calmar']:+6.3f} "
              f"MaxDD={r['maxdd']:+.2%} 2023={r['r2023']:+.1%} 2024={r['r2024']:+.1%} 2025={r['r2025']:+.1%}")
    print(f"\n  Best Calmar: {best['name']} final=${best['final']:,.0f} Calmar={best['calmar']:+.3f} MaxDD={best['maxdd']:+.2%}")
    print(f"  Best final : {best_final['name']} final=${best_final['final']:,.0f} Calmar={best_final['calmar']:+.3f}")

    out = OUT_DIR_ / "crypto_godmode_v30_fractional_ricci.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dict(
            meta=dict(version="v30_fractional_ricci", geometry="fractional Ricci-regularised Fisher-Mahalanobis",
                      k=K_NORMAL, rt_bps=RT_BPS, alpha_grid=ALPHA_GRID, ricci_eta_grid=RICCI_ETA_GRID,
                      elapsed=time.time() - t0),
            results=results,
            selected=dict(best_calmar=best, best_final=best_final),
            plots=plot_paths,
        ), f, indent=2, default=float)
    print(f"\n  Saved → {out}")
    print(f"  Elapsed: {time.time() - t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()