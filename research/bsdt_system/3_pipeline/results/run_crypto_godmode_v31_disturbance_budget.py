"""
run_crypto_godmode_v31_disturbance_budget.py
============================================

v31 = v30 fractional Ricci-Fisher geometry with a corrected G7 disturbance
budget for theta (the action-threshold).

Problem solved
--------------
v30 used  theta = quantile(E_train, q) * max(cond_before / KAPPA_CAP, 1.0)
The cond_before factor was ~3e12 / 20 ~= 1.5e11, blowing theta to ~3e10
even though the regularised metric had cond_after <= KAPPA_CAP. The cap
*already* absorbs the ill-conditioning, so multiplying by cond_before
double-counts the same disturbance.

v31 replaces that with two physically-meaningful disturbance terms,
both evaluated under the regularised metric Sigma_FR:

    rho_reg = ||Sigma_frac - Sigma_FR||_F / ||Sigma_FR||_F   (relative
              Frobenius residual of the regularisation step)
    rho_eta = eta                                             (Ricci shrinkage)

    budget  = sqrt(1 + rho_reg^2 + rho_eta^2)                (Pythagorean)

    theta   = quantile_q(E_train | Sigma_FR) * budget

E_train is now finite and bounded because Sigma_FR has cond <= KAPPA_CAP,
so theta is order-1 in well-scaled units and physically interpretable.

The sweep also varies the quantile q in {0.50, 0.65, 0.80} so we can
verify that the engine is not pathologically sensitive to that knob.

Sweep dimensions
----------------
    alpha in {0.35, 0.50, 0.65, 0.80}      (fractional memory power)
    eta   in {0.00, 0.10}                  (log-Euclidean Ricci shrink)
    q     in {0.50, 0.65, 0.80}            (action-threshold quantile)

Stack
-----
    be50_btc_sol + tbr0p47 + soft_all_micro friction + K=6.5 + RT=6 bps.
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

sys.path.insert(0, str(Path(__file__).parent))

import run_crypto_godmode_v27_all_microstructure as v27
import run_crypto_godmode_v28_canonical_stability as v28
import run_crypto_godmode_v30_fractional_ricci as v30
from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START, TRAIN_START, build_1h_df
from run_crypto_godmode_v1 import KAPPA_A, W_TARGET_A1, build_b_aligned, build_w_star, run_godmode_sweep
from run_crypto_canonical_v4 import A_FACTORS, build_factor_returns
from run_crypto_godmode_v8_multiasset_shell import ASSETS, build_asset_inputs, fetch_futures_ohlcv_symbol
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from simulate_master_strategy import (
    DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR, INIT, equity_metrics, period_table, simulate_combined,
)


BAR = "=" * 112
OUT_DIR_ = Path(OUT_DIR) / "v31_disturbance_budget"
PLOT_DIR = OUT_DIR_ / "plots"

K_NORMAL = 6.5
RT_BPS = 6.0
KAPPA_CAP = 20.0

ALPHA_GRID = [0.35, 0.50, 0.65, 0.80]
RICCI_ETA_GRID = [0.00, 0.10]
Q_GRID = [0.50, 0.65, 0.80]

REG_VARIANT = dict(name="soft_all_micro", tbr_long_min=0.47, tbr_short_max=0.53,
                   soft=True, rho=False, w_funding=0.25, w_oi=0.18,
                   w_lsr=0.16, w_taker=0.16)


def _frob(M: np.ndarray) -> float:
    return float(np.sqrt(np.sum(M * M)))


def disturbance_budget(Sigma_frac: np.ndarray, Sigma_reg: np.ndarray, eta: float) -> dict:
    """Pythagorean budget combining regularisation residual and Ricci shrink."""
    fro_reg = _frob(Sigma_reg)
    rho_reg = _frob(Sigma_frac - Sigma_reg) / max(fro_reg, 1e-12)
    rho_eta = float(eta)
    budget = float(np.sqrt(1.0 + rho_reg ** 2 + rho_eta ** 2))
    return dict(rho_reg=rho_reg, rho_eta=rho_eta, budget=budget)


def theta_v31(b_arr: np.ndarray, train_mask: np.ndarray, Sigma_reg: np.ndarray,
              budget: float, q: float) -> float:
    G = np.linalg.inv(Sigma_reg)
    b_train = b_arr[train_mask]
    E_train = np.einsum("ti,ij,tj->t", b_train, G, b_train)
    base = max(float(np.quantile(E_train, q)), 1e-6)
    return base * budget


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


def row(label: str, sim: dict, test_ts: pd.Timestamp, alpha: float, eta: float, q: float,
        theta: float, sigma_diag: dict, budget_diag: dict) -> dict:
    eq = sim["eq"][sim["eq"].index >= test_ts]
    m = equity_metrics(eq, label)
    yy = yoy(eq)
    return dict(name=label, alpha=alpha, ricci_eta=eta, q=q, theta=theta,
                final=m["final"], profit=m["final"] - INIT, cagr=m["cagr"],
                sharpe=m["sharpe"], maxdd=m["maxdd"], calmar=m["calmar"],
                pct_halted=sim.get("pct_halted", np.nan),
                r2023=yy.get("2023", np.nan), r2024=yy.get("2024", np.nan),
                r2025=yy.get("2025", np.nan), r2026=yy.get("2026", np.nan),
                sigma=sigma_diag, budget=budget_diag)


def plot_theta_landscape(results: list[dict]) -> str:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    rs = sorted(results, key=lambda r: (r["alpha"], r["ricci_eta"], r["q"]))
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Theta vs (alpha, eta, q) — log scale (should be order 1, NOT 1e10).
    keys = [(r["alpha"], r["ricci_eta"]) for r in rs]
    uniq = sorted(set(keys))
    cmap = plt.cm.viridis(np.linspace(0.1, 0.9, len(uniq)))
    for color, (a, e) in zip(cmap, uniq):
        sub = [r for r in rs if r["alpha"] == a and r["ricci_eta"] == e]
        axes[0].plot([r["q"] for r in sub], [r["theta"] for r in sub], "-o",
                     color=color, label=f"a={a:.2f} eta={e:.2f}")
    axes[0].set_xlabel("quantile q"); axes[0].set_ylabel("theta")
    axes[0].set_title("v31 theta landscape (now order-1, not 1e10)")
    axes[0].grid(True, alpha=0.3); axes[0].legend(fontsize=7)

    # Calmar vs q.
    for color, (a, e) in zip(cmap, uniq):
        sub = [r for r in rs if r["alpha"] == a and r["ricci_eta"] == e]
        axes[1].plot([r["q"] for r in sub], [r["calmar"] for r in sub], "-s",
                     color=color, label=f"a={a:.2f} eta={e:.2f}")
    axes[1].set_xlabel("quantile q"); axes[1].set_ylabel("Calmar")
    axes[1].set_title("v31 Calmar sensitivity to theta-quantile")
    axes[1].grid(True, alpha=0.3); axes[1].legend(fontsize=7)

    out = PLOT_DIR / "v31_theta_landscape.png"
    fig.tight_layout(); fig.savefig(out, dpi=170); plt.close(fig)
    return str(out)


def plot_geometry(log_ann: pd.DataFrame, w_star: np.ndarray, test_mask: np.ndarray,
                  Sigma: np.ndarray, best: dict) -> list[str]:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    s = log_ann.iloc[test_mask].copy()
    ws = w_star[test_mask]
    n = len(s)
    idx = np.linspace(0, n - 1, min(n, 4500)).astype(int)
    c = np.linspace(0, 1, len(idx))

    # 2D state-space.
    fig, ax = plt.subplots(figsize=(10, 9))
    ax.scatter(ws[idx, 0], ws[idx, 1], s=7, color="orange", alpha=0.18, label="target w*")
    sc = ax.scatter(s["w_btc"].values[idx], s["w_eth"].values[idx], s=8, c=c,
                    cmap="viridis", alpha=0.78, label="canonical w")
    ax.plot(s["w_btc"].values[idx], s["w_eth"].values[idx], color="steelblue", alpha=0.20, lw=0.7)
    ax.axhline(0, color="black", lw=0.6, alpha=0.5); ax.axvline(0, color="black", lw=0.6, alpha=0.5)
    ax.set_title(f"v31 Disturbance-Budget Engine 2D — alpha={best['alpha']}, "
                 f"eta={best['ricci_eta']}, q={best['q']}, theta={best['theta']:.3f}")
    ax.set_xlabel("w_BTC"); ax.set_ylabel("w_ETH")
    ax.grid(True, alpha=0.22); ax.legend(loc="best")
    cb = fig.colorbar(sc, ax=ax, shrink=0.82); cb.set_label("time through OOS")
    out = PLOT_DIR / "v31_geometry_2d_weights.png"
    fig.tight_layout(); fig.savefig(out, dpi=180); plt.close(fig)
    paths.append(str(out))

    # 3D state-space.
    fig = plt.figure(figsize=(12, 10))
    ax = fig.add_subplot(111, projection="3d")
    ax.scatter(ws[idx, 0], ws[idx, 1], ws[idx, 2], s=5, color="orange", alpha=0.12, label="target w*")
    sc = ax.scatter(s["w_btc"].values[idx], s["w_eth"].values[idx], s["w_sol"].values[idx],
                    s=8, c=c, cmap="viridis", alpha=0.78, label="canonical w")
    ax.plot(s["w_btc"].values[idx], s["w_eth"].values[idx], s["w_sol"].values[idx],
            color="steelblue", alpha=0.22, lw=0.8)
    ax.set_title(f"v31 Disturbance-Budget Engine 3D — theta={best['theta']:.3f}")
    ax.set_xlabel("w_BTC"); ax.set_ylabel("w_ETH"); ax.set_zlabel("w_SOL")
    ax.legend(loc="upper left")
    cb = fig.colorbar(sc, ax=ax, shrink=0.65, pad=0.10); cb.set_label("time through OOS")
    out = PLOT_DIR / "v31_geometry_3d_weights.png"
    fig.tight_layout(); fig.savefig(out, dpi=180); plt.close(fig)
    paths.append(str(out))

    # Energy surface, BTC/ETH plane.
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
    ax.contour(X, Y, Z, levels=[best["theta"]], colors="cyan", linewidths=1.4)
    ax.scatter(s["w_btc"].values[idx], s["w_eth"].values[idx], s=3, c="white", alpha=0.30)
    ax.set_title(f"v31 Energy Surface (cyan = theta level set, theta={best['theta']:.3f})")
    ax.set_xlabel("w_BTC"); ax.set_ylabel("w_ETH")
    cb = fig.colorbar(cs, ax=ax); cb.set_label("energy")
    out = PLOT_DIR / "v31_energy_surface_2d.png"
    fig.tight_layout(); fig.savefig(out, dpi=180); plt.close(fig)
    paths.append(str(out))

    return paths


def main() -> None:
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    print(BAR)
    print("  CRYPTO GODMODE v31 — DISTURBANCE-BUDGET CORRECTED THETA + FRACTIONAL RICCI")
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

    results: list[dict] = []
    artifacts: dict[str, object] = {}
    v27.RT_COST = RT_BPS / 10_000.0

    print(f"\n[2] Sweeping alpha={ALPHA_GRID}, eta={RICCI_ETA_GRID}, q={Q_GRID} ...")
    for alpha in ALPHA_GRID:
        for eta in RICCI_ETA_GRID:
            # Build Sigma once per (alpha, eta); reuse across q.
            Sigma_frac = v30.fractional_covariance(factor_R, train_mask, alpha)
            Sigma_cap, cond = v30.cap_condition(Sigma_frac, KAPPA_CAP)
            Sigma_reg = v30._log_euclidean_shrink_to_identity(Sigma_cap, eta)
            sdiag = dict(alpha=alpha, ricci_eta=eta, **cond,
                         cond_final=float(np.linalg.eigvalsh(Sigma_reg)[-1] /
                                          max(np.linalg.eigvalsh(Sigma_reg)[0], 1e-12)))
            bdiag = disturbance_budget(Sigma_frac, Sigma_reg, eta)
            print(f"\n  [a={alpha:.2f} eta={eta:.2f}] cond {cond['cond_before']:.2e}->{sdiag['cond_final']:.2f} "
                  f"rho_reg={bdiag['rho_reg']:.4f} budget={bdiag['budget']:.4f}")

            for q in Q_GRID:
                label = f"a{alpha:.2f}_r{eta:.2f}_q{q:.2f}".replace(".", "p")
                theta = theta_v31(b_aligned, train_mask, Sigma_reg, bdiag["budget"], q)
                print(f"    [{label}] theta={theta:.5f}")
                log_ann = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned,
                                            Sigma_reg, theta, kappa=KAPPA_A, anneal=True,
                                            label=f"v31_{label}")
                inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                                signal_kind="wstar", use_quadrant=False)
                inputs_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                              signal_kind="wstar", use_quadrant=True)
                inputs = attach_q_hot(inputs_noq, inputs_q)
                sig_map = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}")
                           for asset, _, _, idx in ASSETS}
                unit = v28.run_variant_v28(REG_VARIANT, inputs, sig_map, log_ann)["unit"]
                sim = simulate_k(unit, K_NORMAL)
                r = row(label, sim, test_ts, alpha, eta, q, theta, sdiag, bdiag)
                results.append(r)
                artifacts[label] = dict(Sigma=Sigma_reg, theta=theta, log_ann=log_ann)
                print(f"    [{label}] final=${r['final']:>10,.0f} CAGR={r['cagr']:+7.2%} "
                      f"Calmar={r['calmar']:+6.3f} MaxDD={r['maxdd']:+.2%}")

    best = max(results, key=lambda r: r["calmar"])
    best_final = max(results, key=lambda r: r["final"])
    best_art = artifacts[best["name"]]

    print("\n[3] Saving plots ...")
    landscape = plot_theta_landscape(results)
    print(f"  saved: {landscape}")
    geo_paths = plot_geometry(best_art["log_ann"], w_star, test_mask, best_art["Sigma"], best)
    for p in geo_paths:
        print(f"  saved: {p}")

    print("\n" + BAR)
    print("  v31 RESULTS  (theta is now order-1; rho_reg is the Frobenius regularisation residual)")
    print(BAR)
    for r in sorted(results, key=lambda x: -x["calmar"])[:12]:
        print(f"  {r['name']:<22} a={r['alpha']:.2f} eta={r['ricci_eta']:.2f} q={r['q']:.2f} "
              f"theta={r['theta']:7.3f} final=${r['final']:>10,.0f} "
              f"Calmar={r['calmar']:+6.3f} MaxDD={r['maxdd']:+.2%} "
              f"2023={r['r2023']:+.1%} 2024={r['r2024']:+.1%} 2025={r['r2025']:+.1%}")
    print(f"\n  Best Calmar: {best['name']} final=${best['final']:,.0f} "
          f"Calmar={best['calmar']:+.3f} MaxDD={best['maxdd']:+.2%}")
    print(f"  Best final : {best_final['name']} final=${best_final['final']:,.0f} "
          f"Calmar={best_final['calmar']:+.3f}")

    out = OUT_DIR_ / "crypto_godmode_v31_disturbance_budget.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dict(
            meta=dict(version="v31_disturbance_budget",
                      geometry="fractional Ricci-regularised Fisher-Mahalanobis",
                      theta_rule="quantile_q(E_train|Sigma_reg) * sqrt(1 + rho_reg^2 + eta^2)",
                      k=K_NORMAL, rt_bps=RT_BPS,
                      alpha_grid=ALPHA_GRID, ricci_eta_grid=RICCI_ETA_GRID, q_grid=Q_GRID,
                      kappa_cap=KAPPA_CAP, elapsed=time.time() - t0),
            results=results,
            selected=dict(best_calmar=best, best_final=best_final),
            plots=dict(theta_landscape=landscape, geometry=geo_paths),
        ), f, indent=2, default=float)
    print(f"\n  Saved -> {out}")
    print(f"  Elapsed: {time.time() - t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()
