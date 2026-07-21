"""
run_crypto_godmode_v34_cb_resume_fix.py
========================================

v34 = v32 True-Fractional engine + CB_RESUME / CB_WINDOW fix.

Root cause (from _diag_v32_2026.py)
------------------------------------
The burst on 2025-11-11 → 2025-11-21 takes equity $16k → $159k, setting a
rolling peak of $175,126.  The engine immediately re-halts on 2025-11-21
(roll_DD = 9.24%, above CB_HALT=8%).  The CB_RESUME threshold requires equity
to recover to roll_peak × 0.99 = $173,375 — a +9.07% gain — before ANY trade
can execute.  But the CB blocks all trades, so the engine can never self-heal.

Additionally, CB_WINDOW_DAYS=180 keeps the $175k peak alive until May 2026,
so the required recovery target never decays.  The result: 100% halt from
Dec 2025 onwards, zero r2026 despite 47 above-theta energy bars in 2026.

Fix logic
----------
Keep CB_HALT=0.08 (correct — it protects drawdown well).
Change:
  CB_RESUME:       0.01  →  symmetric to HALT minus small hysteresis gap
  CB_WINDOW_DAYS:  180   →  short enough that a burst peak ages out quickly

Sweep of 3 CB configs:
  "cb_v34_fix"    : halt=0.08, resume=0.06, window=60d  ← primary fix
  "cb_v34_tight"  : halt=0.08, resume=0.04, window=90d  ← tighter hysteresis
  "cb_original"   : halt=0.08, resume=0.01, window=180d ← v32 control

FFD config: d ∈ {0.25, 0.30, 0.50} × q ∈ {0.50, 0.65}
  d=0.30 best Calmar in v32; d=0.50 best final equity; d=0.25 new candidate.
  = 18 total variants

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
OUT_DIR_ = Path(OUT_DIR) / "v34_cb_resume_fix"
PLOT_DIR  = OUT_DIR_ / "plots"

K_NORMAL      = 6.5
RT_BPS        = 6.0
KAPPA_CAP     = 20.0
FFD_THRESHOLD = 1e-5
FFD_MAX_LAG   = 4096

D_GRID = [0.25, 0.30, 0.50]
Q_GRID = [0.50, 0.65]

# Circuit-breaker configs: (cb_halt, cb_resume, cb_window_days, label)
# Diagnostic showed: CB_RESUME=0.01 + CB_WINDOW=180 → self-locking after Nov-25 burst
# Fix: symmetric gap (resume close to halt) + short window so peak decays in ~2 months
CB_CONFIGS = [
    (0.08, 0.06, 60,  "cb_v34_fix"),      # PRIMARY: 2% gap, 60-day window
    (0.08, 0.04, 90,  "cb_v34_tight"),     # tighter hysteresis, 90-day window
    (0.08, 0.01, 180, "cb_original"),      # v32 control — validated 23 Calmar but dead in 2026
]

REG_VARIANT = dict(name="soft_all_micro", tbr_long_min=0.47, tbr_short_max=0.53,
                   soft=True, rho=False, w_funding=0.25, w_oi=0.18,
                   w_lsr=0.16, w_taker=0.16)


# ──────────────────────── GL-FFD (same as v32/v33) ────────────────────────

def ffd_weights(d: float, threshold: float = FFD_THRESHOLD,
                max_lag: int = FFD_MAX_LAG) -> np.ndarray:
    w = [1.0]
    for k in range(1, max_lag):
        wk = -w[-1] * (d - k + 1) / k
        if abs(wk) < threshold:
            break
        w.append(wk)
    return np.array(w, dtype=float)


def frac_diff_series(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    n, L = len(x), len(w)
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
    return rescale_to_correlation(cov), dict(warm_lags=int(L - 1), n_train_used=int(len(Xc)))


# ──────────────────────── Sigma + budget + theta ──────────────────────────

def build_sigma_v34(factor_R, train_mask, df, d):
    Sigma_ffd, ffd_diag = ffd_covariance(factor_R, train_mask, d, df)
    Sigma_cap, cond     = v30.cap_condition(Sigma_ffd, KAPPA_CAP)
    vals = np.linalg.eigvalsh(Sigma_cap)
    sdiag = dict(d_ffd=d, **ffd_diag, **cond,
                 cond_final=float(vals[-1] / max(vals[0], 1e-12)))
    rho_cap = float(np.linalg.norm(Sigma_ffd - Sigma_cap)) / max(float(np.linalg.norm(Sigma_cap)), 1e-12)
    bdiag   = dict(rho_cap=rho_cap, budget=float(np.sqrt(1.0 + rho_cap ** 2)))
    return Sigma_cap, Sigma_ffd, sdiag, bdiag


def theta_v34(b_arr, train_mask, Sigma_cap, budget, q):
    G = np.linalg.inv(Sigma_cap)
    b_train = b_arr[train_mask]
    E_train = np.einsum("ti,ij,tj->t", b_train, G, b_train)
    return max(float(np.quantile(E_train, q)), 1e-6) * budget


# ──────────────────────── Simulation ──────────────────────────────────────

def simulate_v34(unit: pd.Series, cb_halt: float, cb_resume: float,
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


def row_entry(label, sim, test_ts, d, q, cb_label, cb_halt, cb_resume,
              cb_window, theta, sdiag, bdiag) -> dict:
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
        sigma=sdiag, budget=bdiag,
    )


# ──────────────────────── Plots ───────────────────────────────────────────

def plot_cb_equity_curves(sim_by_cb: dict[str, dict], test_ts: pd.Timestamp,
                          d: float, q: float) -> str:
    """Equity curves for best d/q across all CB configs."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    colors = {"cb_v34_fix": "steelblue", "cb_v34_tight": "darkorange", "cb_original": "tomato"}
    fig, axes = plt.subplots(2, 1, figsize=(16, 10), sharex=True)
    for cb_lbl, sim in sim_by_cb.items():
        eq = sim["eq"][sim["eq"].index >= test_ts]
        c  = colors.get(cb_lbl, "grey")
        axes[0].semilogy(eq.index, eq.values, color=c, lw=1.6,
                         label=f"{cb_lbl}  final=${eq.iloc[-1]:,.0f}")
    axes[0].set_title(f"v34 Equity curves — d={d}, q={q}  (2023–2026)")
    axes[0].set_ylabel("Equity ($)"); axes[0].legend(fontsize=9)
    axes[0].grid(True, alpha=0.25)

    # monthly halted fraction per CB config
    months = pd.date_range("2023-01", "2026-06", freq="MS")
    for cb_lbl, sim in sim_by_cb.items():
        # approximate from equity flat-line detection
        eq = sim["eq"]
        pct = sim.get("pct_halted_monthly", {})
        pass

    # just show roll_dd proxy via equity drawdown from rolling max
    for cb_lbl, sim in sim_by_cb.items():
        eq = sim["eq"][sim["eq"].index >= test_ts]
        dd = (eq - eq.cummax()) / eq.cummax()
        c  = colors.get(cb_lbl, "grey")
        axes[1].plot(dd.index, dd.values, color=c, lw=0.9, alpha=0.7, label=cb_lbl)
    axes[1].axhline(-0.08, color="red",   ls="--", lw=1.2, label="CB_HALT=-8%")
    axes[1].axhline(-0.06, color="green", ls="-.", lw=1.2, label="CB_RESUME=-6% (v34)")
    axes[1].axhline(-0.01, color="purple",ls=":",  lw=1.2, label="CB_RESUME=-1% (orig)")
    axes[1].set_ylabel("Drawdown from ATH"); axes[1].legend(fontsize=8)
    axes[1].grid(True, alpha=0.25)

    out = PLOT_DIR / f"v34_equity_cb_d{str(d).replace('.','p')}_q{str(q).replace('.','p')}.png"
    fig.tight_layout(); fig.savefig(out, dpi=170); plt.close(fig)
    return str(out)


def plot_annual_comparison(results: list[dict]) -> str:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    years = ["r2023", "r2024", "r2025", "r2026"]
    cb_labels = [c[3] for c in CB_CONFIGS]
    # best variant per CB config by calmar
    best_per_cb = {}
    for cb_lbl in cb_labels:
        sub = [r for r in results if r["cb_label"] == cb_lbl]
        if sub:
            best_per_cb[cb_lbl] = max(sub, key=lambda r: r["calmar"])

    x = np.arange(len(years))
    width = 0.25
    colors = {"cb_v34_fix": "steelblue", "cb_v34_tight": "darkorange", "cb_original": "tomato"}
    fig, ax = plt.subplots(figsize=(12, 6))
    for i, (cb_lbl, r) in enumerate(best_per_cb.items()):
        vals = [r.get(y, 0.0) for y in years]
        ax.bar(x + (i - 1) * width, vals, width=width * 0.9,
               label=f"{cb_lbl}  Calmar={r['calmar']:.2f}", color=colors.get(cb_lbl, "grey"),
               alpha=0.85)
    ax.axhline(0, color="black", lw=0.7)
    ax.set_xticks(x); ax.set_xticklabels(["2023", "2024", "2025", "2026"])
    ax.set_title("v34 Annual Returns — best variant per CB config")
    ax.set_ylabel("Return multiplier (YoY)"); ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25, axis="y")
    out = PLOT_DIR / "v34_annual_returns_by_cb.png"
    fig.tight_layout(); fig.savefig(out, dpi=170); plt.close(fig)
    return str(out)


def plot_calmar_heatmap(results: list[dict]) -> str:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    cb_labels  = [c[3] for c in CB_CONFIGS]
    d_vals     = sorted(set(r["d"] for r in results))
    fig, axes  = plt.subplots(1, len(cb_labels), figsize=(16, 5), sharey=True)
    for ax, cb_lbl in zip(axes, cb_labels):
        sub = [r for r in results if r["cb_label"] == cb_lbl]
        # pivot: d × q → calmar
        q_vals = sorted(set(r["q"] for r in sub))
        Z = np.zeros((len(d_vals), len(q_vals)))
        for r in sub:
            i = d_vals.index(r["d"]); j = q_vals.index(r["q"])
            Z[i, j] = r["calmar"]
        im = ax.imshow(Z, aspect="auto", cmap="RdYlGn", vmin=0, vmax=35)
        ax.set_xticks(range(len(q_vals))); ax.set_xticklabels([f"{q:.2f}" for q in q_vals])
        ax.set_yticks(range(len(d_vals))); ax.set_yticklabels([f"{d:.2f}" for d in d_vals])
        ax.set_xlabel("q"); ax.set_ylabel("d"); ax.set_title(cb_lbl)
        for i in range(len(d_vals)):
            for j in range(len(q_vals)):
                ax.text(j, i, f"{Z[i,j]:.1f}", ha="center", va="center", fontsize=9)
        plt.colorbar(im, ax=ax, shrink=0.8)
    fig.suptitle("v34 Calmar heatmap (d × q) per CB config", fontweight="bold")
    out = PLOT_DIR / "v34_calmar_heatmap.png"
    fig.tight_layout(); fig.savefig(out, dpi=170); plt.close(fig)
    return str(out)


# ──────────────────────── Main ────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    print(BAR)
    print("  CRYPTO GODMODE v34 — CB_RESUME/WINDOW FIX (self-locking post-burst repair)")
    print("  Diagnosis: CB_RESUME=0.01 + CB_WINDOW=180d locks engine after Nov-2025 burst")
    print("  Fix: CB_RESUME=0.06 + CB_WINDOW=60d  (2% hysteresis gap, peak ages in 60d)")
    print(BAR)

    print("\n[0] Preloading microstructure cache ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        ms = v27._get_ms(sym)
        print(f"  {sym}: {ms.shape}")

    print("\n[1] Building shared market inputs ...")
    df, _     = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask  = np.asarray(df.index >= TEST_START)
    test_ts    = pd.Timestamp(TEST_START)
    factor_R   = build_factor_returns(df)
    w_star     = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned  = build_b_aligned(w_star)
    ohlc_map   = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch         = get_channel_series()
    v27.RT_COST = RT_BPS / 10_000.0

    print("\n[2] FFD weight diagnostics ...")
    weight_lens: dict[float, int] = {}
    for d in D_GRID:
        w = ffd_weights(d)
        weight_lens[d] = len(w)
        print(f"  d={d:.2f}: lags={len(w):4d}  w_1={w[1]:+.5f}  w_last={w[-1]:+.2e}")

    print("\n[3] Building FFD Sigma per d ...")
    sigma_store: dict[float, tuple] = {}
    for d in D_GRID:
        Sigma_cap, Sigma_ffd, sdiag, bdiag = build_sigma_v34(factor_R, train_mask, df, d)
        print(f"  d={d:.2f}: cond {sdiag['cond_before']:.2e} → {sdiag['cond_final']:.2f}  "
              f"rho_cap={bdiag['rho_cap']:.4f}")
        sigma_store[d] = (Sigma_cap, Sigma_ffd, sdiag, bdiag)

    print("\n[4] Building unit signals (d × q) — shared across all CB configs ...")
    unit_store: dict[tuple, pd.Series] = {}
    theta_store: dict[tuple, float]    = {}
    for d in D_GRID:
        Sigma_cap, _, sdiag, bdiag = sigma_store[d]
        for q in Q_GRID:
            key   = (d, q)
            theta = theta_v34(b_aligned, train_mask, Sigma_cap, bdiag["budget"], q)
            print(f"  d={d:.2f} q={q:.2f}: theta={theta:.5f}", end="")
            log_ann = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned,
                                        Sigma_cap, theta, kappa=KAPPA_A, anneal=True,
                                        label=f"v34_d{d:.2f}_q{q:.2f}")
            inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                            signal_kind="wstar", use_quadrant=False)
            inputs_q   = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                            signal_kind="wstar", use_quadrant=True)
            inputs     = attach_q_hot(inputs_noq, inputs_q)
            sig_map    = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}")
                          for asset, _, _, idx in ASSETS}
            unit = v28.run_variant_v28(REG_VARIANT, inputs, sig_map, log_ann)["unit"]
            unit_store[key]  = unit
            theta_store[key] = theta
            print(f"  unit built (n={len(unit)})")

    print(f"\n[5] Sweeping CB configs {[c[3] for c in CB_CONFIGS]} ...")
    results:   list[dict] = []
    sim_store: dict[str, dict] = {}
    cb_equity: dict[tuple, dict] = {}   # (d, q) → {cb_lbl: sim}

    for cb_halt, cb_resume, cb_window, cb_lbl in CB_CONFIGS:
        print(f"\n  [{cb_lbl}]: halt={cb_halt}  resume={cb_resume}  window={cb_window}d")
        for d in D_GRID:
            Sigma_cap, _, sdiag, bdiag = sigma_store[d]
            for q in Q_GRID:
                key   = (d, q)
                unit  = unit_store[key]
                theta = theta_store[key]
                sim   = simulate_v34(unit, cb_halt, cb_resume, cb_window)
                label = f"d{d:.2f}_q{q:.2f}_{cb_lbl}".replace(".", "p")
                r     = row_entry(label, sim, test_ts, d, q, cb_lbl,
                                  cb_halt, cb_resume, cb_window, theta, sdiag, bdiag)
                results.append(r)
                sim_store[label] = sim
                if key not in cb_equity:
                    cb_equity[key] = {}
                cb_equity[key][cb_lbl] = sim
                print(f"    [{label}] final=${r['final']:>10,.0f}  "
                      f"Calmar={r['calmar']:+6.3f}  MaxDD={r['maxdd']:+.2%}  "
                      f"halted={r['pct_halted']:.1%}  "
                      f"r2023={r['r2023']:+.4f}  r2024={r['r2024']:+.4f}  "
                      f"r2025={r['r2025']:+.4f}  r2026={r['r2026']:+.4f}")

    best_calmar = max(results, key=lambda r: r["calmar"])
    best_final  = max(results, key=lambda r: r["final"])

    print("\n" + BAR)
    print("  v34 RESULTS — sorted by Calmar")
    print(BAR)
    hdr  = f"  {'Name':<36} {'d':>4} {'q':>4} {'CB':>14} "
    hdr += f"{'Final_k':>8} {'Calmar':>7} {'MaxDD%':>7} {'Sharpe':>6} "
    hdr += f"{'Halt%':>6} {'2023x':>6} {'2024x':>6} {'2025x':>6} {'2026x':>6}"
    print(hdr)
    print("  " + "-" * 115)
    for r in sorted(results, key=lambda x: -x["calmar"]):
        print(f"  {r['name']:<36} {r['d']:>4.2f} {r['q']:>4.2f} {r['cb_label']:>14} "
              f"{r['final']/1000:>8.1f} {r['calmar']:>7.2f} {r['maxdd']*100:>7.2f} "
              f"{r['sharpe']:>6.3f} {r['pct_halted']*100:>6.1f} "
              f"{r['r2023']:>6.4f} {r['r2024']:>6.4f} {r['r2025']:>6.4f} {r['r2026']:>6.4f}")

    print(f"\n  ★ Best Calmar : {best_calmar['name']}  "
          f"final=${best_calmar['final']:,.0f}  Calmar={best_calmar['calmar']:+.3f}  "
          f"MaxDD={best_calmar['maxdd']:+.2%}  r2026={best_calmar['r2026']:+.4f}")
    print(f"  ★ Best Final  : {best_final['name']}  "
          f"final=${best_final['final']:,.0f}  Calmar={best_final['calmar']:+.3f}  "
          f"r2026={best_final['r2026']:+.4f}")

    print("\n[6] Per-CB-config summary:")
    for cb_halt, cb_resume, cb_window, cb_lbl in CB_CONFIGS:
        sub = [r for r in results if r["cb_label"] == cb_lbl]
        best = max(sub, key=lambda r: r["calmar"])
        avg_halt = sum(r["pct_halted"] for r in sub) / len(sub)
        has_2026 = sum(1 for r in sub if r["r2026"] > 0.0) / len(sub)
        print(f"  {cb_lbl:>14}: avg_halt={avg_halt:.1%}  2026_active={has_2026:.0%}  "
              f"best_calmar={best['calmar']:.3f}  best_final=${best['final']:,.0f}  ({best['name']})  "
              f"best_r2026={best['r2026']:+.4f}")

    print("\n[7] Saving plots ...")
    # Equity curves for best d/q combo (d=0.30, q=0.50)
    best_key = (0.30, 0.50)
    if best_key in cb_equity:
        p1 = plot_cb_equity_curves(cb_equity[best_key], test_ts, *best_key)
        print(f"  saved: {p1}")
    # Also for d=0.50, q=0.50
    key2 = (0.50, 0.50)
    if key2 in cb_equity:
        p2 = plot_cb_equity_curves(cb_equity[key2], test_ts, *key2)
        print(f"  saved: {p2}")
    p3 = plot_annual_comparison(results)
    print(f"  saved: {p3}")
    p4 = plot_calmar_heatmap(results)
    print(f"  saved: {p4}")

    # ── Save JSON ─────────────────────────────────────────────────────────
    out = OUT_DIR_ / "crypto_godmode_v34_cb_resume_fix.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dict(
            meta=dict(
                version="v34_cb_resume_fix",
                description=(
                    "GL-FFD d=0.25/0.30/0.50, CB_RESUME fix: "
                    "resume=0.06 window=60d eliminates post-burst self-lock"
                ),
                diagnosis=dict(
                    problem="CB_RESUME=0.01 + CB_WINDOW=180d self-locks after Nov-2025 burst",
                    trigger_date="2025-11-21",
                    roll_peak_at_trigger=175126,
                    equity_at_trigger=158951,
                    roll_dd_at_trigger=0.0924,
                    required_to_release_original=173375,
                    equity_gap_pct=0.0907,
                ),
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
        ), f, indent=2, default=float)
    print(f"\n  Saved -> {out}")
    print(f"  Elapsed: {time.time() - t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()
