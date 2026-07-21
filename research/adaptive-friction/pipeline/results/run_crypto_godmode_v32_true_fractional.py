"""
run_crypto_godmode_v32_true_fractional.py
==========================================

v32 = TRUE fractional calculus engine.

What "fractional" actually means here
-------------------------------------
v30/v31 used a power-law-weighted covariance and called it fractional.
That is just an exponentially-similar weighting scheme, not fractional
calculus. v32 implements two genuine fractional operators:

(A) FRACTIONAL DIFFERENCING (Grunwald-Letnikov / Lopez de Prado)
    Apply the operator (1 - L)^d, d in (0, 1), to log-prices to obtain
    fractionally-differenced returns r^{(d)}.  Coefficients
        w_0 = 1, w_k = w_{k-1} * -(d - k + 1) / k
    Truncated when |w_k| < 1e-5 (standard FFD threshold).  Unlike the
    integer first difference (d = 1) which destroys memory, fractional
    differencing produces a stationary series that preserves long
    memory at order H = d + 1/2.  This is the canonical operator in
    Lopez de Prado, Advances in Financial Machine Learning ch. 5.

(B) FRACTIONAL LAPLACIAN RICCI FLOW on the SPD log-Euclidean cone
    Standard log-Euclidean Ricci shrink: log_lambda_i -> (1-eta) log_lambda_i
    Fractional Laplacian s in (0, 1):    log_lambda_i -> sign * |log_lambda_i|^{1 - s}
    So s -> 0 collapses to identity, s = 1 is the standard linear shrink,
    s in (0,1) is the genuine fractional smoothing -- it pulls the spectrum
    toward isotropy at a sub-linear rate, as in the heat semigroup
    e^{-t (-Delta)^s}.

Geometry
--------
    G_t = Sigma_FL^{-1}
where Sigma_FL is the empirical covariance of fractionally-differenced
factor returns, condition-capped, then fractionally smoothed.

Theta uses the v31 disturbance budget (now also accounting for the
fractional smoothing residual rho_frac in the Pythagorean sum).

Sweep
-----
    d_grid = {0.30, 0.50, 0.70}        fractional differencing order
    s_grid = {0.00, 0.30, 0.60}        fractional Laplacian order (0 = no smoothing)
    q_grid = {0.50, 0.65}              theta quantile

Stack
-----
    be50_btc_sol + tbr0p47 + soft_all_micro + K = 6.5 + RT = 6 bps
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
from run_crypto_canonical_v4 import A_FACTORS, build_factor_returns, rescale_to_correlation
from run_crypto_godmode_v8_multiasset_shell import ASSETS, build_asset_inputs, fetch_futures_ohlcv_symbol
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from simulate_master_strategy import (
    DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR, INIT, equity_metrics, period_table, simulate_combined,
)


BAR = "=" * 112
OUT_DIR_ = Path(OUT_DIR) / "v32_true_fractional"
PLOT_DIR = OUT_DIR_ / "plots"

K_NORMAL = 6.5
RT_BPS = 6.0
KAPPA_CAP = 20.0
FFD_THRESHOLD = 1e-5
FFD_MAX_LAG = 4096

D_GRID = [0.30, 0.50, 0.70]
S_GRID = [0.00, 0.30, 0.60]
Q_GRID = [0.50, 0.65]

REG_VARIANT = dict(name="soft_all_micro", tbr_long_min=0.47, tbr_short_max=0.53,
                   soft=True, rho=False, w_funding=0.25, w_oi=0.18,
                   w_lsr=0.16, w_taker=0.16)


# ---------- (A) Fractional differencing (Grunwald-Letnikov) ----------

def ffd_weights(d: float, threshold: float = FFD_THRESHOLD, max_lag: int = FFD_MAX_LAG) -> np.ndarray:
    """Grunwald-Letnikov coefficients of (1 - L)^d, truncated when |w| < threshold."""
    w = [1.0]
    for k in range(1, max_lag):
        wk = -w[-1] * (d - k + 1) / k
        if abs(wk) < threshold:
            break
        w.append(wk)
    return np.array(w, dtype=float)


def frac_diff_series(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Apply fixed-width FFD with weights w to a 1D array (NaN before warm-up)."""
    n = len(x)
    L = len(w)
    out = np.full(n, np.nan)
    if n < L:
        return out
    # convolve manually using sliding dot product (faster than np.convolve for moderate L).
    for t in range(L - 1, n):
        out[t] = float(np.dot(w, x[t - L + 1: t + 1][::-1]))
    return out


def fractional_factor_returns(df: pd.DataFrame, factor_R: np.ndarray, d: float) -> tuple[np.ndarray, int]:
    """
    Replace integer first-difference returns with FFD of order d applied to
    cumulative log factor 'prices'.  Returns the ffd factor matrix plus the
    warm-up index (rows before that are NaN/dropped from training).
    """
    R = np.nan_to_num(factor_R, nan=0.0)
    P = np.cumsum(R, axis=0)              # synthetic factor log-prices
    w = ffd_weights(d)
    L = len(w)
    F = np.full_like(P, np.nan, dtype=float)
    for j in range(P.shape[1]):
        F[:, j] = frac_diff_series(P[:, j], w)
    return F, L - 1


def ffd_covariance(factor_R: np.ndarray, train_mask: np.ndarray, d: float, df: pd.DataFrame) -> tuple[np.ndarray, dict]:
    F, warm = fractional_factor_returns(df, factor_R, d)
    valid = train_mask & np.all(np.isfinite(F), axis=1)
    X = F[valid]
    mu = X.mean(axis=0)
    Xc = X - mu
    cov = (Xc.T @ Xc) / max(len(Xc) - 1, 1)
    Sigma = rescale_to_correlation(cov)
    return Sigma, dict(warm_lags=int(warm), n_train_used=int(len(Xc)))


# ---------- (B) Fractional Laplacian Ricci flow on SPD ----------

def fractional_laplacian_smoothing(Sigma: np.ndarray, s: float) -> np.ndarray:
    """
    Apply (-Delta)^s heat-semigroup style smoothing on log-Euclidean cone:
        log_lambda_i  ->  sign(log_lambda_i) * |log_lambda_i|^{1 - s}
    s = 0 : identity; s = 1 : full collapse to identity matrix.
    """
    if s <= 0:
        return Sigma
    M = (Sigma + Sigma.T) / 2
    vals, vecs = np.linalg.eigh(M)
    vals = np.clip(vals, 1e-12, None)
    log_v = np.log(vals)
    new_log = np.sign(log_v) * np.power(np.abs(log_v), max(1.0 - s, 0.0))
    new_v = np.exp(new_log)
    S = (vecs * new_v) @ vecs.T
    d = np.sqrt(np.diag(S))
    return S / np.outer(d, d)


def build_v32_sigma(factor_R: np.ndarray, train_mask: np.ndarray, df: pd.DataFrame,
                    d: float, s: float) -> tuple[np.ndarray, np.ndarray, dict]:
    """Returns (Sigma_reg, Sigma_ffd_raw, diag)."""
    Sigma_ffd, ffd_diag = ffd_covariance(factor_R, train_mask, d, df)
    Sigma_cap, cond = v30.cap_condition(Sigma_ffd, KAPPA_CAP)
    Sigma_reg = fractional_laplacian_smoothing(Sigma_cap, s)
    vals = np.linalg.eigvalsh(Sigma_reg)
    diag = dict(d_ffd=d, s_frac=s, **ffd_diag, **cond,
                cond_final=float(vals[-1] / max(vals[0], 1e-12)),
                eigvals=[float(x) for x in vals])
    return Sigma_reg, Sigma_ffd, diag


# ---------- Theta with extended disturbance budget ----------

def disturbance_budget_v32(Sigma_ffd: np.ndarray, Sigma_cap: np.ndarray, Sigma_reg: np.ndarray, s: float) -> dict:
    fro_reg = float(np.linalg.norm(Sigma_reg))
    rho_cap = float(np.linalg.norm(Sigma_ffd - Sigma_cap)) / max(fro_reg, 1e-12)
    rho_frac = float(np.linalg.norm(Sigma_cap - Sigma_reg)) / max(fro_reg, 1e-12)
    rho_s = float(s)
    budget = float(np.sqrt(1.0 + rho_cap ** 2 + rho_frac ** 2 + rho_s ** 2))
    return dict(rho_cap=rho_cap, rho_frac=rho_frac, rho_s=rho_s, budget=budget)


def theta_v32(b_arr: np.ndarray, train_mask: np.ndarray, Sigma_reg: np.ndarray,
              budget: float, q: float) -> float:
    G = np.linalg.inv(Sigma_reg)
    b_train = b_arr[train_mask]
    E_train = np.einsum("ti,ij,tj->t", b_train, G, b_train)
    base = max(float(np.quantile(E_train, q)), 1e-6)
    return base * budget


# ---------- Sim helpers ----------

def simulate_k(unit: pd.Series, k: float = K_NORMAL) -> dict:
    return simulate_combined(
        unit_normal=unit, unit_crash=pd.Series(0.0, index=unit.index),
        K_normal=k, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=v28.CB_HALT, cb_resume=v28.CB_RESUME, cb_window_days=v28.CB_WINDOW_DAYS,
        use_cb=True,
    )


def yoy(eq: pd.Series) -> dict[str, float]:
    return {r["period"][:4]: r["return_pct"] for r in period_table(eq, "Y")}


def row(label: str, sim: dict, test_ts: pd.Timestamp, d: float, s: float, q: float,
        theta: float, sigma_diag: dict, budget_diag: dict) -> dict:
    eq = sim["eq"][sim["eq"].index >= test_ts]
    m = equity_metrics(eq, label)
    yy = yoy(eq)
    return dict(name=label, d=d, s_frac=s, q=q, theta=theta,
                final=m["final"], profit=m["final"] - INIT, cagr=m["cagr"],
                sharpe=m["sharpe"], maxdd=m["maxdd"], calmar=m["calmar"],
                pct_halted=sim.get("pct_halted", np.nan),
                r2023=yy.get("2023", np.nan), r2024=yy.get("2024", np.nan),
                r2025=yy.get("2025", np.nan), r2026=yy.get("2026", np.nan),
                sigma=sigma_diag, budget=budget_diag)


# ---------- Plots ----------

def plot_ffd_weights(d_list: list[float]) -> str:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 6))
    for d in d_list:
        w = ffd_weights(d)
        ax.plot(w, label=f"d={d:.2f}  (truncated at k={len(w)})")
    ax.axhline(0, color="black", lw=0.5)
    ax.set_title("v32 Grunwald-Letnikov FFD weights w_k for (1-L)^d")
    ax.set_xlabel("lag k"); ax.set_ylabel("w_k"); ax.set_xscale("log")
    ax.grid(True, alpha=0.3); ax.legend()
    out = PLOT_DIR / "v32_ffd_weights.png"
    fig.tight_layout(); fig.savefig(out, dpi=170); plt.close(fig)
    return str(out)


def plot_landscape(results: list[dict]) -> str:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    rs = sorted(results, key=lambda r: (r["d"], r["s_frac"], r["q"]))
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    keys = sorted({(r["d"], r["s_frac"]) for r in rs})
    cmap = plt.cm.plasma(np.linspace(0.1, 0.9, len(keys)))
    for color, (d, s) in zip(cmap, keys):
        sub = [r for r in rs if r["d"] == d and r["s_frac"] == s]
        axes[0].plot([r["q"] for r in sub], [r["theta"] for r in sub], "-o",
                     color=color, label=f"d={d:.2f} s={s:.2f}")
        axes[1].plot([r["q"] for r in sub], [r["calmar"] for r in sub], "-s",
                     color=color, label=f"d={d:.2f} s={s:.2f}")
    axes[0].set_xlabel("quantile q"); axes[0].set_ylabel("theta")
    axes[0].set_title("v32 theta landscape (FFD + frac Laplacian)")
    axes[0].grid(True, alpha=0.3); axes[0].legend(fontsize=7)
    axes[1].set_xlabel("quantile q"); axes[1].set_ylabel("Calmar")
    axes[1].set_title("v32 Calmar across (d, s, q)")
    axes[1].grid(True, alpha=0.3); axes[1].legend(fontsize=7)
    out = PLOT_DIR / "v32_landscape.png"
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

    fig, ax = plt.subplots(figsize=(10, 9))
    ax.scatter(ws[idx, 0], ws[idx, 1], s=7, color="orange", alpha=0.18, label="target w*")
    sc = ax.scatter(s["w_btc"].values[idx], s["w_eth"].values[idx], s=8, c=c,
                    cmap="viridis", alpha=0.78, label="canonical w")
    ax.plot(s["w_btc"].values[idx], s["w_eth"].values[idx], color="steelblue", alpha=0.20, lw=0.7)
    ax.axhline(0, color="black", lw=0.6, alpha=0.5); ax.axvline(0, color="black", lw=0.6, alpha=0.5)
    ax.set_title(f"v32 True Fractional Engine 2D - d={best['d']}, s={best['s_frac']}, "
                 f"q={best['q']}, theta={best['theta']:.3f}")
    ax.set_xlabel("w_BTC"); ax.set_ylabel("w_ETH")
    ax.grid(True, alpha=0.22); ax.legend(loc="best")
    cb = fig.colorbar(sc, ax=ax, shrink=0.82); cb.set_label("time through OOS")
    out = PLOT_DIR / "v32_geometry_2d_weights.png"
    fig.tight_layout(); fig.savefig(out, dpi=180); plt.close(fig)
    paths.append(str(out))

    fig = plt.figure(figsize=(12, 10))
    ax = fig.add_subplot(111, projection="3d")
    ax.scatter(ws[idx, 0], ws[idx, 1], ws[idx, 2], s=5, color="orange", alpha=0.12, label="target w*")
    sc = ax.scatter(s["w_btc"].values[idx], s["w_eth"].values[idx], s["w_sol"].values[idx],
                    s=8, c=c, cmap="viridis", alpha=0.78, label="canonical w")
    ax.plot(s["w_btc"].values[idx], s["w_eth"].values[idx], s["w_sol"].values[idx],
            color="steelblue", alpha=0.22, lw=0.8)
    ax.set_title(f"v32 True Fractional Engine 3D - d={best['d']}, s={best['s_frac']}")
    ax.set_xlabel("w_BTC"); ax.set_ylabel("w_ETH"); ax.set_zlabel("w_SOL")
    ax.legend(loc="upper left")
    cb = fig.colorbar(sc, ax=ax, shrink=0.65, pad=0.10); cb.set_label("time through OOS")
    out = PLOT_DIR / "v32_geometry_3d_weights.png"
    fig.tight_layout(); fig.savefig(out, dpi=180); plt.close(fig)
    paths.append(str(out))

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
    ax.set_title(f"v32 Fisher Energy Surface - cyan = theta={best['theta']:.3f}")
    ax.set_xlabel("w_BTC"); ax.set_ylabel("w_ETH")
    cb = fig.colorbar(cs, ax=ax); cb.set_label("energy")
    out = PLOT_DIR / "v32_energy_surface_2d.png"
    fig.tight_layout(); fig.savefig(out, dpi=180); plt.close(fig)
    paths.append(str(out))
    return paths


# ---------- Main ----------

def main() -> None:
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    print(BAR)
    print("  CRYPTO GODMODE v32 - TRUE FRACTIONAL CALCULUS ENGINE (FFD + frac. Laplacian Ricci)")
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

    print("\n[2] FFD weight diagnostics (saving plot) ...")
    weight_lens = {}
    for d in D_GRID:
        w = ffd_weights(d)
        weight_lens[d] = len(w)
        print(f"  d={d:.2f}: lags used = {len(w):4d}  w_1 = {w[1]:+.5f}  w_last = {w[-1]:+.2e}")
    plot_ffd_weights(D_GRID)

    results: list[dict] = []
    artifacts: dict[str, object] = {}
    v27.RT_COST = RT_BPS / 10_000.0

    print(f"\n[3] Sweeping d={D_GRID}, s={S_GRID}, q={Q_GRID} ...")
    for d in D_GRID:
        for s_frac in S_GRID:
            Sigma_ffd, ffd_diag = ffd_covariance(factor_R, train_mask, d, df)
            Sigma_cap, cond = v30.cap_condition(Sigma_ffd, KAPPA_CAP)
            Sigma_reg = fractional_laplacian_smoothing(Sigma_cap, s_frac)
            vals = np.linalg.eigvalsh(Sigma_reg)
            sdiag = dict(d_ffd=d, s_frac=s_frac, **ffd_diag, **cond,
                         cond_final=float(vals[-1] / max(vals[0], 1e-12)))
            bdiag = disturbance_budget_v32(Sigma_ffd, Sigma_cap, Sigma_reg, s_frac)
            print(f"\n  [d={d:.2f} s={s_frac:.2f}] cond {cond['cond_before']:.2e}->{sdiag['cond_final']:.2f} "
                  f"rho_cap={bdiag['rho_cap']:.4f} rho_frac={bdiag['rho_frac']:.4f} budget={bdiag['budget']:.4f}")
            for q in Q_GRID:
                label = f"d{d:.2f}_s{s_frac:.2f}_q{q:.2f}".replace(".", "p")
                theta = theta_v32(b_aligned, train_mask, Sigma_reg, bdiag["budget"], q)
                print(f"    [{label}] theta={theta:.5f}")
                log_ann = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned,
                                            Sigma_reg, theta, kappa=KAPPA_A, anneal=True,
                                            label=f"v32_{label}")
                inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                                signal_kind="wstar", use_quadrant=False)
                inputs_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                              signal_kind="wstar", use_quadrant=True)
                inputs = attach_q_hot(inputs_noq, inputs_q)
                sig_map = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}")
                           for asset, _, _, idx in ASSETS}
                unit = v28.run_variant_v28(REG_VARIANT, inputs, sig_map, log_ann)["unit"]
                sim = simulate_k(unit, K_NORMAL)
                r = row(label, sim, test_ts, d, s_frac, q, theta, sdiag, bdiag)
                results.append(r)
                artifacts[label] = dict(Sigma=Sigma_reg, theta=theta, log_ann=log_ann)
                print(f"    [{label}] final=${r['final']:>10,.0f} CAGR={r['cagr']:+7.2%} "
                      f"Calmar={r['calmar']:+6.3f} MaxDD={r['maxdd']:+.2%}")

    best = max(results, key=lambda r: r["calmar"])
    best_final = max(results, key=lambda r: r["final"])
    best_art = artifacts[best["name"]]

    print("\n[4] Saving plots ...")
    landscape = plot_landscape(results)
    print(f"  saved: {landscape}")
    geo_paths = plot_geometry(best_art["log_ann"], w_star, test_mask, best_art["Sigma"], best)
    for p in geo_paths:
        print(f"  saved: {p}")

    print("\n" + BAR)
    print("  v32 RESULTS  (true fractional calculus: FFD + fractional Laplacian Ricci)")
    print(BAR)
    for r in sorted(results, key=lambda x: -x["calmar"]):
        print(f"  {r['name']:<22} d={r['d']:.2f} s={r['s_frac']:.2f} q={r['q']:.2f} "
              f"theta={r['theta']:7.3f} final=${r['final']:>10,.0f} "
              f"Calmar={r['calmar']:+6.3f} MaxDD={r['maxdd']:+.2%} "
              f"2023={r['r2023']:+.1%} 2024={r['r2024']:+.1%} 2025={r['r2025']:+.1%}")
    print(f"\n  Best Calmar: {best['name']} final=${best['final']:,.0f} "
          f"Calmar={best['calmar']:+.3f} MaxDD={best['maxdd']:+.2%}")
    print(f"  Best final : {best_final['name']} final=${best_final['final']:,.0f} "
          f"Calmar={best_final['calmar']:+.3f}")

    out = OUT_DIR_ / "crypto_godmode_v32_true_fractional.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dict(
            meta=dict(version="v32_true_fractional",
                      operators=dict(
                          ffd="Grunwald-Letnikov fixed-width fractional differencing on log-prices",
                          frac_laplacian="log-Euclidean (-Delta)^s smoothing on SPD cone",
                      ),
                      d_grid=D_GRID, s_grid=S_GRID, q_grid=Q_GRID,
                      kappa_cap=KAPPA_CAP, ffd_threshold=FFD_THRESHOLD,
                      k=K_NORMAL, rt_bps=RT_BPS,
                      ffd_weight_lengths={f"{d:.2f}": int(weight_lens[d]) for d in D_GRID},
                      elapsed=time.time() - t0),
            results=results,
            selected=dict(best_calmar=best, best_final=best_final),
            plots=dict(landscape=landscape, geometry=geo_paths,
                       ffd_weights=str(PLOT_DIR / "v32_ffd_weights.png")),
        ), f, indent=2, default=float)
    print(f"\n  Saved -> {out}")
    print(f"  Elapsed: {time.time() - t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()
