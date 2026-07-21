"""
run_crypto_godmode_v33_cb_fix.py
=================================

v33 = v32 True-Fractional engine + Circuit-Breaker redesign.

Root-cause analysis of v32 (91.5% halt, r2026=0)
--------------------------------------------------
v28 inherited CB params:  CB_HALT=0.08, CB_RESUME=0.01, CB_WINDOW_DAYS=180
This creates a strongly asymmetric circuit breaker:
  - EASY to trigger  : rolling 180-day equity DD >= 8%
  - HARD to exit     : rolling 180-day DD must fall back below 1%
                       (i.e., equity must be within 1% of its rolling 180-day high)
Once triggered during a volatile period (e.g. late 2025 after the 10× run),
the system permanently stays halted because CB_RESUME=0.01 is almost
impossible to satisfy when the rolling peak is at an all-time high.
Result: r2026 = 0.0000 for every v32 variant.

v33 fixes
---------
(A) SYMMETRIC CB — open gap between halt and resume thresholds:
        CB_HALT         0.08 → 0.15   (allow larger rolling dip before halting)
        CB_RESUME       0.01 → 0.10   (resume when within 10% of rolling peak)
        CB_WINDOW_DAYS  180  → 90     (shorter lookback = faster recovery)

(B) DROP fractional Laplacian (s_frac) — v32 confirmed it destructs equity
    at every tested level.  Set S_GRID = [0.0] only.

(C) FINER D_GRID — v32 best Calmar was at d=0.3 (long memory).  Sweep
    d ∈ {0.20, 0.30, 0.40, 0.50, 0.70} to better resolve the optimal.

(D) CB sweep — also test the v28-original CB (0.08/0.01/180) as control,
    plus two new candidates:
        "balanced" : CB_HALT=0.15, CB_RESUME=0.10, CB_WINDOW_DAYS=90
        "loose"    : CB_HALT=0.18, CB_RESUME=0.13, CB_WINDOW_DAYS=90  (simulator default)

Fractional operators — identical to v32
----------------------------------------
(A) Grunwald-Letnikov FFD of order d ∈ (0,1) on log-prices
(B) No fractional Laplacian (s=0 fixed)

Sweep: d_grid × cb_grid × q_grid
    d:  {0.20, 0.30, 0.40, 0.50, 0.70}
    cb: {(0.08,0.01,180), (0.15,0.10,90), (0.18,0.13,90)}
    q:  {0.50, 0.65}
  = 30 variants

Stack: be50_btc_sol + tbr0p47 + soft_all_micro + K=6.5 + RT=6bps
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
OUT_DIR_ = Path(OUT_DIR) / "v33_cb_fix"
PLOT_DIR  = OUT_DIR_ / "plots"

K_NORMAL      = 6.5
RT_BPS        = 6.0
KAPPA_CAP     = 20.0
FFD_THRESHOLD = 1e-5
FFD_MAX_LAG   = 4096

D_GRID  = [0.20, 0.30, 0.40, 0.50, 0.70]
Q_GRID  = [0.50, 0.65]

# Circuit-breaker configs: (cb_halt, cb_resume, cb_window_days, label)
CB_CONFIGS = [
    (0.08, 0.01, 180, "cb_original"),   # v28 / v32 control — likely dead in 2026
    (0.15, 0.10,  90, "cb_balanced"),   # v33 fix — symmetric 5% gap, 90-day window
    (0.18, 0.13,  90, "cb_loose"),      # simulator default
]

REG_VARIANT = dict(name="soft_all_micro", tbr_long_min=0.47, tbr_short_max=0.53,
                   soft=True, rho=False, w_funding=0.25, w_oi=0.18,
                   w_lsr=0.16, w_taker=0.16)


# ──────────────────────── Grunwald-Letnikov FFD ───────────────────────────

def ffd_weights(d: float, threshold: float = FFD_THRESHOLD,
                max_lag: int = FFD_MAX_LAG) -> np.ndarray:
    """GL coefficients of (1-L)^d, truncated when |w_k| < threshold."""
    w = [1.0]
    for k in range(1, max_lag):
        wk = -w[-1] * (d - k + 1) / k
        if abs(wk) < threshold:
            break
        w.append(wk)
    return np.array(w, dtype=float)


def frac_diff_series(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Apply fixed-width FFD with weights w to 1D array (NaN before warmup)."""
    n = len(x)
    L = len(w)
    out = np.full(n, np.nan)
    if n < L:
        return out
    for t in range(L - 1, n):
        out[t] = float(np.dot(w, x[t - L + 1: t + 1][::-1]))
    return out


def ffd_covariance(factor_R: np.ndarray, train_mask: np.ndarray,
                   d: float, df: pd.DataFrame) -> tuple[np.ndarray, dict]:
    R = np.nan_to_num(factor_R, nan=0.0)
    P = np.cumsum(R, axis=0)
    w = ffd_weights(d)
    L = len(w)
    F = np.full_like(P, np.nan, dtype=float)
    for j in range(P.shape[1]):
        F[:, j] = frac_diff_series(P[:, j], w)
    valid = train_mask & np.all(np.isfinite(F), axis=1)
    X = F[valid]
    mu = X.mean(axis=0)
    Xc = X - mu
    cov = (Xc.T @ Xc) / max(len(Xc) - 1, 1)
    Sigma = rescale_to_correlation(cov)
    return Sigma, dict(warm_lags=int(L - 1), n_train_used=int(len(Xc)))


# ──────────────────────── Conditioning + Theta ────────────────────────────

def build_v33_sigma(factor_R: np.ndarray, train_mask: np.ndarray,
                    df: pd.DataFrame, d: float) -> tuple[np.ndarray, dict]:
    Sigma_ffd, ffd_diag = ffd_covariance(factor_R, train_mask, d, df)
    Sigma_cap, cond = v30.cap_condition(Sigma_ffd, KAPPA_CAP)
    vals = np.linalg.eigvalsh(Sigma_cap)
    sdiag = dict(d_ffd=d, **ffd_diag, **cond,
                 cond_final=float(vals[-1] / max(vals[0], 1e-12)))
    return Sigma_cap, sdiag


def disturbance_budget_v33(Sigma_ffd: np.ndarray, Sigma_cap: np.ndarray) -> dict:
    fro_reg = float(np.linalg.norm(Sigma_cap))
    rho_cap = float(np.linalg.norm(Sigma_ffd - Sigma_cap)) / max(fro_reg, 1e-12)
    budget  = float(np.sqrt(1.0 + rho_cap ** 2))
    return dict(rho_cap=rho_cap, budget=budget)


def theta_v33(b_arr: np.ndarray, train_mask: np.ndarray,
              Sigma_cap: np.ndarray, budget: float, q: float) -> float:
    G = np.linalg.inv(Sigma_cap)
    b_train = b_arr[train_mask]
    E_train = np.einsum("ti,ij,tj->t", b_train, G, b_train)
    base = max(float(np.quantile(E_train, q)), 1e-6)
    return base * budget


# ──────────────────────── Simulation wrapper ──────────────────────────────

def simulate_k(unit: pd.Series, cb_halt: float, cb_resume: float,
               cb_window_days: int, k: float = K_NORMAL) -> dict:
    return simulate_combined(
        unit_normal=unit, unit_crash=pd.Series(0.0, index=unit.index),
        K_normal=k, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=cb_halt, cb_resume=cb_resume,
        cb_window_days=cb_window_days, use_cb=True,
    )


def yoy(eq: pd.Series) -> dict[str, float]:
    return {r["period"][:4]: r["return_pct"] for r in period_table(eq, "Y")}


def row_entry(label: str, sim: dict, test_ts: pd.Timestamp,
              d: float, q: float, cb_label: str, cb_halt: float,
              cb_resume: float, cb_window: int, theta: float,
              sigma_diag: dict, budget_diag: dict) -> dict:
    eq = sim["eq"][sim["eq"].index >= test_ts]
    m  = equity_metrics(eq, label)
    yy = yoy(eq)
    return dict(
        name=label, d=d, q=q, cb_label=cb_label,
        cb_halt=cb_halt, cb_resume=cb_resume, cb_window_days=cb_window,
        theta=theta,
        final=m["final"], profit=m["final"] - INIT, cagr=m["cagr"],
        sharpe=m["sharpe"], maxdd=m["maxdd"], calmar=m["calmar"],
        pct_halted=sim.get("pct_halted", np.nan),
        n_trips=sim.get("n_trips", 0),
        r2023=yy.get("2023", np.nan), r2024=yy.get("2024", np.nan),
        r2025=yy.get("2025", np.nan), r2026=yy.get("2026", np.nan),
        sigma=sigma_diag, budget=budget_diag,
    )


# ──────────────────────── Plots ───────────────────────────────────────────

def plot_ffd_weights(d_list: list[float]) -> str:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 6))
    for d in d_list:
        w = ffd_weights(d)
        ax.plot(w, label=f"d={d:.2f}  (k={len(w)} lags)")
    ax.axhline(0, color="black", lw=0.5)
    ax.set_title("v33 GL-FFD weights w_k for (1-L)^d")
    ax.set_xlabel("lag k"); ax.set_ylabel("w_k"); ax.set_xscale("log")
    ax.grid(True, alpha=0.3); ax.legend()
    out = PLOT_DIR / "v33_ffd_weights.png"
    fig.tight_layout(); fig.savefig(out, dpi=170); plt.close(fig)
    return str(out)


def plot_cb_comparison(results: list[dict]) -> str:
    """Plot Calmar and final equity grouped by CB config and d."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    cb_labels = [c[3] for c in CB_CONFIGS]
    colors = {"cb_original": "tomato", "cb_balanced": "steelblue", "cb_loose": "mediumseagreen"}
    markers = {cb: m for cb, m in zip(cb_labels, ["o", "s", "^"])}

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    for cb_lbl in cb_labels:
        sub = [r for r in results if r["cb_label"] == cb_lbl]
        sub_best_q = {}
        for r in sub:
            key = r["d"]
            if key not in sub_best_q or r["calmar"] > sub_best_q[key]["calmar"]:
                sub_best_q[key] = r
        sub_sorted = sorted(sub_best_q.values(), key=lambda x: x["d"])
        ds   = [r["d"] for r in sub_sorted]
        cal  = [r["calmar"] for r in sub_sorted]
        fin  = [r["final"] / 1000 for r in sub_sorted]
        halt = [r["pct_halted"] * 100 for r in sub_sorted]
        c = colors[cb_lbl]
        axes[0].plot(ds, cal,  color=c, marker=markers[cb_lbl], label=cb_lbl, lw=1.8, ms=8)
        axes[1].plot(ds, fin,  color=c, marker=markers[cb_lbl], label=cb_lbl, lw=1.8, ms=8)
        axes[2].plot(ds, halt, color=c, marker=markers[cb_lbl], label=cb_lbl, lw=1.8, ms=8)

    axes[0].set_title("Calmar vs d (best q)");  axes[0].set_xlabel("d"); axes[0].set_ylabel("Calmar")
    axes[1].set_title("Final equity ($k) vs d"); axes[1].set_xlabel("d"); axes[1].set_ylabel("Final ($k)")
    axes[2].set_title("% Halted vs d");          axes[2].set_xlabel("d"); axes[2].set_ylabel("% Halted")
    for ax in axes:
        ax.grid(True, alpha=0.3); ax.legend(fontsize=9)
    fig.suptitle("v33 CB Fix: Circuit-Breaker Comparison", fontsize=13, fontweight="bold")
    out = PLOT_DIR / "v33_cb_comparison.png"
    fig.tight_layout(); fig.savefig(out, dpi=170); plt.close(fig)
    return str(out)


def plot_annual_returns(results: list[dict], top_n: int = 6) -> str:
    """Bar chart of annual returns for top-N variants by Calmar."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    top = sorted(results, key=lambda r: r["calmar"], reverse=True)[:top_n]
    years = ["r2023", "r2024", "r2025", "r2026"]
    x = np.arange(len(years))
    width = 0.8 / len(top)
    fig, ax = plt.subplots(figsize=(13, 6))
    for i, r in enumerate(top):
        vals = [r.get(y, 0.0) for y in years]
        ax.bar(x + i * width - 0.4 + width / 2, vals,
               width=width * 0.9, label=r["name"], alpha=0.85)
    ax.axhline(0, color="black", lw=0.7)
    ax.set_xticks(x); ax.set_xticklabels(["2023", "2024", "2025", "2026"])
    ax.set_title(f"v33 Annual Returns — top {top_n} by Calmar")
    ax.set_ylabel("Return multiplier (YoY)"); ax.legend(fontsize=7)
    ax.grid(True, alpha=0.25, axis="y")
    out = PLOT_DIR / "v33_annual_returns.png"
    fig.tight_layout(); fig.savefig(out, dpi=170); plt.close(fig)
    return str(out)


def plot_equity_curves(sim_store: dict, top_n: int = 6, test_ts: pd.Timestamp = None) -> str:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    top_names = list(list(sim_store.keys()))[:top_n]
    fig, ax = plt.subplots(figsize=(14, 7))
    cmap = plt.cm.tab10(np.linspace(0, 1, len(top_names)))
    for color, name in zip(cmap, top_names):
        eq = sim_store[name]["eq"]
        if test_ts is not None:
            eq = eq[eq.index >= test_ts]
        ax.semilogy(eq.index, eq.values, color=color, lw=1.4, label=name, alpha=0.85)
    ax.set_title("v33 Equity curves — top variants by Calmar")
    ax.set_ylabel("Equity ($)"); ax.set_xlabel("Date")
    ax.axhline(INIT, color="grey", ls="--", lw=0.7, label="start")
    ax.grid(True, alpha=0.25); ax.legend(fontsize=7)
    out = PLOT_DIR / "v33_equity_curves.png"
    fig.tight_layout(); fig.savefig(out, dpi=170); plt.close(fig)
    return str(out)


# ──────────────────────── Main ────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    print(BAR)
    print("  CRYPTO GODMODE v33 — GL-FFD FRACTIONAL + CB FIX")
    print(BAR)

    print("\n[0] Preloading microstructure cache ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        ms = v27._get_ms(sym)
        print(f"  {sym}: {ms.shape}")

    print("\n[1] Building shared market inputs ...")
    df, _ = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask  = np.asarray(df.index >= TEST_START)
    test_ts    = pd.Timestamp(TEST_START)
    factor_R   = build_factor_returns(df)
    w_star     = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned  = build_b_aligned(w_star)
    ohlc_map   = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch         = get_channel_series()

    print("\n[2] FFD weight diagnostics ...")
    weight_lens: dict[float, int] = {}
    for d in D_GRID:
        w = ffd_weights(d)
        weight_lens[d] = len(w)
        print(f"  d={d:.2f}: lags={len(w):4d}  w_1={w[1]:+.5f}  w_last={w[-1]:+.2e}")
    plot_ffd_weights(D_GRID)

    # Pre-build Sigma per d (Sigma does not depend on CB config or q)
    print("\n[3] Building FFD covariances ...")
    sigma_store: dict[float, tuple[np.ndarray, np.ndarray, dict, dict]] = {}
    for d in D_GRID:
        Sigma_ffd, ffd_diag = ffd_covariance(factor_R, train_mask, d, df)
        Sigma_cap, cond     = v30.cap_condition(Sigma_ffd, KAPPA_CAP)
        vals = np.linalg.eigvalsh(Sigma_cap)
        sdiag = dict(d_ffd=d, **ffd_diag, **cond,
                     cond_final=float(vals[-1] / max(vals[0], 1e-12)))
        bdiag = disturbance_budget_v33(Sigma_ffd, Sigma_cap)
        print(f"  d={d:.2f}: cond {cond['cond_before']:.2e} → {sdiag['cond_final']:.2f}  "
              f"rho_cap={bdiag['rho_cap']:.4f}  budget={bdiag['budget']:.4f}")
        sigma_store[d] = (Sigma_cap, Sigma_ffd, sdiag, bdiag)

    # Pre-build unit signals per d × q (CB config does NOT affect the signal generation)
    print("\n[4] Building unit signals (d × q) ...")
    unit_store: dict[tuple, pd.Series] = {}
    log_ann_store: dict[float, pd.DataFrame] = {}
    for d in D_GRID:
        Sigma_cap, _, sdiag, bdiag = sigma_store[d]
        if d not in log_ann_store:
            # Run the godmode geometry once per d (same for all q, rerun for theta but cheap)
            pass
        for q in Q_GRID:
            theta = theta_v33(b_aligned, train_mask, Sigma_cap, bdiag["budget"], q)
            print(f"  d={d:.2f} q={q:.2f}: theta={theta:.5f}", end="")
            log_ann = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned,
                                        Sigma_cap, theta, kappa=KAPPA_A, anneal=True,
                                        label=f"v33_d{d:.2f}_q{q:.2f}")
            log_ann_store[(d, q)] = log_ann
            inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                            signal_kind="wstar", use_quadrant=False)
            inputs_q   = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                            signal_kind="wstar", use_quadrant=True)
            inputs     = attach_q_hot(inputs_noq, inputs_q)
            sig_map    = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}")
                          for asset, _, _, idx in ASSETS}
            unit = v28.run_variant_v28(REG_VARIANT, inputs, sig_map, log_ann)["unit"]
            unit_store[(d, q)] = unit
            print(f"  unit built (n={len(unit)})")

    # Sweep CB configs
    print(f"\n[5] Sweeping CB configs {[c[3] for c in CB_CONFIGS]} ...")
    results:   list[dict] = []
    sim_store: dict[str, dict] = {}

    for cb_halt, cb_resume, cb_window, cb_lbl in CB_CONFIGS:
        print(f"\n  CB [{cb_lbl}]: halt={cb_halt} resume={cb_resume} window={cb_window}d")
        for d in D_GRID:
            Sigma_cap, _, sdiag, bdiag = sigma_store[d]
            for q in Q_GRID:
                label = f"d{d:.2f}_q{q:.2f}_{cb_lbl}".replace(".", "p")
                unit  = unit_store[(d, q)]
                sim   = simulate_k(unit, cb_halt, cb_resume, cb_window, K_NORMAL)
                r = row_entry(label, sim, test_ts, d, q, cb_lbl,
                              cb_halt, cb_resume, cb_window,
                              theta_v33(b_aligned, train_mask, Sigma_cap, bdiag["budget"], q),
                              sdiag, bdiag)
                results.append(r)
                sim_store[label] = sim
                print(f"    [{label}] final=${r['final']:>10,.0f}  Calmar={r['calmar']:+6.3f}  "
                      f"MaxDD={r['maxdd']:+.2%}  halted={r['pct_halted']:.1%}  "
                      f"r2026={r['r2026']:+.4f}")

    # ── Summary table ──────────────────────────────────────────────────────
    best_calmar = max(results, key=lambda r: r["calmar"])
    best_final  = max(results, key=lambda r: r["final"])

    print("\n" + BAR)
    print("  v33 RESULTS — sorted by Calmar")
    print(BAR)
    hdr = f"  {'Name':<32} {'d':>4} {'q':>4} {'CB':>12} {'Final_k':>8} {'Calmar':>7} {'MaxDD%':>7} "
    hdr += f"{'Sharpe':>6} {'Halt%':>6} {'2023x':>6} {'2024x':>6} {'2025x':>6} {'2026x':>6}"
    print(hdr)
    print("  " + "-" * 110)
    for r in sorted(results, key=lambda x: -x["calmar"]):
        print(f"  {r['name']:<32} {r['d']:>4.2f} {r['q']:>4.2f} {r['cb_label']:>12} "
              f"{r['final']/1000:>8.1f} {r['calmar']:>7.2f} {r['maxdd']*100:>7.2f} "
              f"{r['sharpe']:>6.3f} {r['pct_halted']*100:>6.1f} "
              f"{r['r2023']:>6.4f} {r['r2024']:>6.4f} {r['r2025']:>6.4f} {r['r2026']:>6.4f}")

    print(f"\n  ★ Best Calmar : {best_calmar['name']}  "
          f"final=${best_calmar['final']:,.0f}  Calmar={best_calmar['calmar']:+.3f}  "
          f"MaxDD={best_calmar['maxdd']:+.2%}")
    print(f"  ★ Best Final  : {best_final['name']}  "
          f"final=${best_final['final']:,.0f}  Calmar={best_final['calmar']:+.3f}")

    print("\n[6] Saving plots ...")
    p1 = plot_ffd_weights(D_GRID)
    p2 = plot_cb_comparison(results)
    p3 = plot_annual_returns(results)
    # equity curves: top 6 by calmar
    top6 = [r["name"] for r in sorted(results, key=lambda x: -x["calmar"])[:6]]
    top6_sims = {n: sim_store[n] for n in top6 if n in sim_store}
    p4 = plot_equity_curves(top6_sims, top_n=6, test_ts=test_ts)
    for p in [p1, p2, p3, p4]:
        print(f"  saved: {p}")

    # ── CB group summary ──────────────────────────────────────────────────
    print("\n[7] Per-CB-config summary:")
    for cb_halt, cb_resume, cb_window, cb_lbl in CB_CONFIGS:
        sub = [r for r in results if r["cb_label"] == cb_lbl]
        best = max(sub, key=lambda r: r["calmar"])
        avg_halt = sum(r["pct_halted"] for r in sub) / len(sub)
        has_2026 = sum(1 for r in sub if r["r2026"] > 0.0) / len(sub)
        print(f"  {cb_lbl:>14}: avg_halt={avg_halt:.1%}  2026_active={has_2026:.0%}  "
              f"best_calmar={best['calmar']:.3f}  best_final=${best['final']:,.0f}  ({best['name']})")

    # ── Save JSON ─────────────────────────────────────────────────────────
    out = OUT_DIR_ / "crypto_godmode_v33_cb_fix.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dict(
            meta=dict(
                version="v33_cb_fix",
                description="GL-FFD fractional engine + CB asymmetry fix (drop s_frac)",
                d_grid=D_GRID, q_grid=Q_GRID,
                cb_configs=[{"cb_halt": c[0], "cb_resume": c[1],
                              "cb_window_days": c[2], "label": c[3]} for c in CB_CONFIGS],
                kappa_cap=KAPPA_CAP, ffd_threshold=FFD_THRESHOLD,
                k=K_NORMAL, rt_bps=RT_BPS,
                ffd_weight_lengths={f"{d:.2f}": int(weight_lens[d]) for d in D_GRID},
                elapsed=time.time() - t0,
            ),
            results=results,
            selected=dict(best_calmar=best_calmar, best_final=best_final),
            plots=dict(ffd_weights=p1, cb_comparison=p2,
                       annual_returns=p3, equity_curves=p4),
        ), f, indent=2, default=float)
    print(f"\n  Saved -> {out}")
    print(f"  Elapsed: {time.time() - t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()
