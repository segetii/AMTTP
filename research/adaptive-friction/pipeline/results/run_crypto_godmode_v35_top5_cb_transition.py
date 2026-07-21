"""
run_crypto_godmode_v35_top5_cb_transition.py
=============================================

v35 = Top-5 (d,q) variants from v34 × fine CB transition-zone sweep.

Motivation
----------
v34 exposed a performance cliff between:
  cb_original  (window=180, resume=0.01)  → Calmar=23, MaxDD=-15%, r2026=0.00
  cb_v34_tight (window= 90, resume=0.04)  → Calmar=17, MaxDD=-35%, r2026=0.07

We want to find where exactly the "self-locking" breaks and MaxDD blows up:
  • Is it the window length (180→90)?
  • Is it the resume level (0.01→0.04)?
  • Is there a sweet spot keeping MaxDD < 25% while activating 2026?

Strategy
---------
Fix halt=0.08.
Sweep:
  CB_WINDOW  ∈ {90, 105, 120, 150, 180}
  CB_RESUME  ∈ {0.01, 0.02, 0.03, 0.04}
  + cb_original (0.01/180) as control (duplicate — explicit label)

Total CB configs: 5×4 + 1 control = 21

Top-5 (d,q) variants (ranked by Calmar in v34 cb_original):
  1. (d=0.30, q=0.50)  Calmar=23.00
  2. (d=0.30, q=0.65)  Calmar=23.00
  3. (d=0.25, q=0.50)  Calmar=22.55
  4. (d=0.25, q=0.65)  Calmar=22.44
  5. (d=0.50, q=0.65)  Calmar=20.28

Total variants: 5 × 21 = 105  (CB is fast once unit signals built)
Expected runtime: ~550–650s
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
import matplotlib.colors as mcolors

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

BAR = "=" * 120
OUT_DIR_ = Path(OUT_DIR) / "v35_top5_cb_transition"
PLOT_DIR  = OUT_DIR_ / "plots"

K_NORMAL      = 6.5
RT_BPS        = 6.0
KAPPA_CAP     = 20.0
FFD_THRESHOLD = 1e-5
FFD_MAX_LAG   = 4096

# ── Top-5 (d,q) from v34 cb_original, ranked by Calmar ────────────────────
TOP5 = [
    (0.30, 0.50),   # rank 1  Calmar=23.00
    (0.30, 0.65),   # rank 2  Calmar=23.00
    (0.25, 0.50),   # rank 3  Calmar=22.55
    (0.25, 0.65),   # rank 4  Calmar=22.44
    (0.50, 0.65),   # rank 5  Calmar=20.28
]

CB_HALT = 0.08

# Fine transition-zone grid around the v34 cliff
CB_WINDOWS  = [90, 105, 120, 150, 180]
CB_RESUMES  = [0.01, 0.02, 0.03, 0.04]

def _make_cb_configs() -> list[tuple[float, float, int, str]]:
    configs: list[tuple[float, float, int, str]] = []
    for window in CB_WINDOWS:
        for resume in CB_RESUMES:
            label = f"w{window:03d}_r{int(resume*100):02d}"
            configs.append((CB_HALT, resume, window, label))
    # Add explicit control alias so it appears in summaries even though
    # (w180, r01) is already in the grid
    configs.append((CB_HALT, 0.01, 180, "cb_original"))
    return configs

CB_CONFIGS = _make_cb_configs()

REG_VARIANT = dict(name="soft_all_micro", tbr_long_min=0.47, tbr_short_max=0.53,
                   soft=True, rho=False, w_funding=0.25, w_oi=0.18,
                   w_lsr=0.16, w_taker=0.16)


# ──────────────────────── GL-FFD ─────────────────────────────────────────

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


def ffd_covariance(factor_R: np.ndarray, train_mask: np.ndarray, d: float,
                   df: pd.DataFrame) -> tuple[np.ndarray, dict]:
    R = np.nan_to_num(factor_R, nan=0.0)
    P = np.cumsum(R, axis=0)
    w = ffd_weights(d)
    L = len(w)
    F = np.full_like(P, np.nan, dtype=float)
    for j in range(P.shape[1]):
        F[:, j] = frac_diff_series(P[:, j], w)
    valid = train_mask & np.all(np.isfinite(F), axis=1)
    X  = F[valid]
    mu = X.mean(axis=0)
    Xc = X - mu
    cov = (Xc.T @ Xc) / max(len(Xc) - 1, 1)
    return rescale_to_correlation(cov), dict(warm_lags=int(L - 1), n_train_used=int(len(Xc)))


# ──────────────────────── Sigma / theta ───────────────────────────────────

def build_sigma(factor_R, train_mask, df, d):
    Sigma_ffd, ffd_diag = ffd_covariance(factor_R, train_mask, d, df)
    Sigma_cap, cond     = v30.cap_condition(Sigma_ffd, KAPPA_CAP)
    vals  = np.linalg.eigvalsh(Sigma_cap)
    sdiag = dict(d_ffd=d, **ffd_diag, **cond,
                 cond_final=float(vals[-1] / max(vals[0], 1e-12)))
    rho_cap = float(np.linalg.norm(Sigma_ffd - Sigma_cap)) / max(float(np.linalg.norm(Sigma_cap)), 1e-12)
    bdiag   = dict(rho_cap=rho_cap, budget=float(np.sqrt(1.0 + rho_cap ** 2)))
    return Sigma_cap, Sigma_ffd, sdiag, bdiag


def theta_from(b_arr, train_mask, Sigma_cap, budget, q):
    G       = np.linalg.inv(Sigma_cap)
    b_train = b_arr[train_mask]
    E_train = np.einsum("ti,ij,tj->t", b_train, G, b_train)
    return max(float(np.quantile(E_train, q)), 1e-6) * budget


# ──────────────────────── Simulation ──────────────────────────────────────

def simulate_unit(unit: pd.Series, cb_halt: float, cb_resume: float,
                  cb_window_days: int) -> dict:
    return simulate_combined(
        unit_normal=unit, unit_crash=pd.Series(0.0, index=unit.index),
        K_normal=K_NORMAL, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=cb_halt, cb_resume=cb_resume,
        cb_window_days=cb_window_days, use_cb=True,
    )


def yoy(eq: pd.Series) -> dict[str, float]:
    return {r["period"][:4]: r["return_pct"] for r in period_table(eq, "Y")}


def result_row(label, sim, test_ts, d, q, cb_label, cb_halt, cb_resume,
               cb_window, theta, sdiag, bdiag) -> dict:
    eq = sim["eq"][sim["eq"].index >= test_ts]
    m  = equity_metrics(eq, label)
    yy = yoy(eq)
    return dict(
        name=label, d=d, q=q, rank=TOP5.index((d, q)) + 1,
        cb_label=cb_label, cb_halt=cb_halt, cb_resume=cb_resume, cb_window_days=cb_window,
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

def plot_calmar_surface(results: list[dict]) -> list[str]:
    """One heatmap per (d,q) rank: MaxDD and Calmar vs (window, resume)."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for rank_idx, (d, q) in enumerate(TOP5, start=1):
        sub = [r for r in results
               if r["d"] == d and r["q"] == q and r["cb_label"] != "cb_original"]
        if not sub:
            continue
        windows = sorted(set(r["cb_window_days"] for r in sub))
        resumes = sorted(set(r["cb_resume"]       for r in sub))
        C = np.zeros((len(resumes), len(windows)))
        M = np.zeros((len(resumes), len(windows)))
        for r in sub:
            i = resumes.index(r["cb_resume"])
            j = windows.index(r["cb_window_days"])
            C[i, j] = r["calmar"]
            M[i, j] = r["maxdd"] * 100

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        for ax, Z, title, cmap, vmin, vmax, fmt in [
            (axes[0], C, "Calmar", "RdYlGn", 0,   30, "{:.1f}"),
            (axes[1], M, "MaxDD (%)", "RdYlGn_r", -50, -5, "{:.1f}"),
        ]:
            im = ax.imshow(Z, aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax)
            ax.set_xticks(range(len(windows)))
            ax.set_xticklabels([str(w) for w in windows])
            ax.set_yticks(range(len(resumes)))
            ax.set_yticklabels([f"{r:.2f}" for r in resumes])
            ax.set_xlabel("CB_WINDOW_DAYS"); ax.set_ylabel("CB_RESUME")
            ax.set_title(title)
            for i in range(len(resumes)):
                for j in range(len(windows)):
                    ax.text(j, i, fmt.format(Z[i, j]),
                            ha="center", va="center", fontsize=8)
            plt.colorbar(im, ax=ax, shrink=0.8)
        fig.suptitle(f"v35 Rank-{rank_idx}: d={d}, q={q}  (halt=0.08)",
                     fontweight="bold")
        out = PLOT_DIR / f"v35_surface_rank{rank_idx}_d{str(d).replace('.','p')}_q{str(q).replace('.','p')}.png"
        fig.tight_layout(); fig.savefig(out, dpi=170); plt.close(fig)
        paths.append(str(out))
    return paths


def plot_r2026_surface(results: list[dict]) -> list[str]:
    """r2026 and halt% vs (window, resume) for each top-5 variant."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for rank_idx, (d, q) in enumerate(TOP5, start=1):
        sub = [r for r in results
               if r["d"] == d and r["q"] == q and r["cb_label"] != "cb_original"]
        if not sub:
            continue
        windows = sorted(set(r["cb_window_days"] for r in sub))
        resumes = sorted(set(r["cb_resume"]       for r in sub))
        R26 = np.zeros((len(resumes), len(windows)))
        HLT = np.zeros((len(resumes), len(windows)))
        for r in sub:
            i = resumes.index(r["cb_resume"])
            j = windows.index(r["cb_window_days"])
            R26[i, j] = r["r2026"]
            HLT[i, j] = r["pct_halted"] * 100

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        for ax, Z, title, cmap, vmin, vmax, fmt in [
            (axes[0], R26, "r2026 (YoY mult)", "RdYlGn", -0.5, 2.0, "{:.3f}"),
            (axes[1], HLT, "Halt% (2023–2026)", "RdYlGn_r", 70, 95, "{:.1f}"),
        ]:
            im = ax.imshow(Z, aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax)
            ax.set_xticks(range(len(windows)))
            ax.set_xticklabels([str(w) for w in windows])
            ax.set_yticks(range(len(resumes)))
            ax.set_yticklabels([f"{r:.2f}" for r in resumes])
            ax.set_xlabel("CB_WINDOW_DAYS"); ax.set_ylabel("CB_RESUME")
            ax.set_title(title)
            for i in range(len(resumes)):
                for j in range(len(windows)):
                    ax.text(j, i, fmt.format(Z[i, j]),
                            ha="center", va="center", fontsize=8)
            plt.colorbar(im, ax=ax, shrink=0.8)
        fig.suptitle(f"v35 Rank-{rank_idx}: d={d}, q={q} — r2026 / halt% grid",
                     fontweight="bold")
        out = PLOT_DIR / f"v35_r2026_rank{rank_idx}_d{str(d).replace('.','p')}_q{str(q).replace('.','p')}.png"
        fig.tight_layout(); fig.savefig(out, dpi=170); plt.close(fig)
        paths.append(str(out))
    return paths


def plot_equity_curves_top5(sim_store: dict[str, dict],
                            best_per_rank: list[dict], test_ts: pd.Timestamp) -> str:
    """Equity curves: cb_original vs best-new-CB for each rank variant."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(len(TOP5), 1, figsize=(16, 4 * len(TOP5)), sharex=True)
    colors = plt.cm.tab10.colors
    for ax_i, (rank_idx, (d, q)) in enumerate(enumerate(TOP5, 1)):
        ax = axes[ax_i]
        # cb_original baseline
        orig_key = f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}_cb_original"
        if orig_key in sim_store:
            eq = sim_store[orig_key]["eq"]
            eq = eq[eq.index >= test_ts]
            ax.semilogy(eq.index, eq.values, color="tomato", lw=1.4,
                        label=f"cb_original  ${eq.iloc[-1]:,.0f}")
        # best new CB by calmar
        best = best_per_rank[ax_i]
        best_key = best["name"]
        if best_key in sim_store:
            eq2 = sim_store[best_key]["eq"]
            eq2 = eq2[eq2.index >= test_ts]
            ax.semilogy(eq2.index, eq2.values, color=colors[ax_i % 10], lw=1.6,
                        label=f"{best['cb_label']}  ${eq2.iloc[-1]:,.0f}  "
                              f"Calmar={best['calmar']:.2f}  r2026={best['r2026']:+.4f}")
        ax.set_title(f"Rank-{rank_idx}: d={d}, q={q}")
        ax.set_ylabel("Equity ($)"); ax.legend(fontsize=8); ax.grid(True, alpha=0.25)
    axes[-1].set_xlabel("Date")
    fig.suptitle("v35 Top-5 variants: cb_original vs best new CB", fontweight="bold", y=1.01)
    out = PLOT_DIR / "v35_equity_top5_best_vs_orig.png"
    fig.tight_layout(); fig.savefig(out, dpi=170, bbox_inches="tight"); plt.close(fig)
    return str(out)


def plot_cliff_profile(results: list[dict]) -> str:
    """For rank-1 (d=0.30,q=0.50): show Calmar, MaxDD, r2026 as function of window
    for each resume value — the 'cliff profile'."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    d, q = TOP5[0]
    sub = [r for r in results if r["d"] == d and r["q"] == q and r["cb_label"] != "cb_original"]
    windows = sorted(set(r["cb_window_days"] for r in sub))
    resumes = sorted(set(r["cb_resume"]       for r in sub))
    colors_r = {rv: c for rv, c in zip(resumes, ["steelblue","darkorange","forestgreen","purple"])}

    fig, axes = plt.subplots(3, 1, figsize=(13, 11), sharex=True)
    for resume in resumes:
        rows = sorted([r for r in sub if r["cb_resume"] == resume],
                      key=lambda r: r["cb_window_days"])
        ws = [r["cb_window_days"] for r in rows]
        c  = colors_r[resume]
        axes[0].plot(ws, [r["calmar"]       for r in rows], marker="o", color=c,
                     label=f"resume={resume:.2f}")
        axes[1].plot(ws, [r["maxdd"] * 100  for r in rows], marker="o", color=c)
        axes[2].plot(ws, [r["r2026"]        for r in rows], marker="o", color=c)

    # Mark v34 reference points
    orig_sub = [r for r in results if r["d"] == d and r["q"] == q
                and r["cb_label"] == "cb_original"]
    if orig_sub:
        o = orig_sub[0]
        for ax, val in zip(axes, [o["calmar"], o["maxdd"]*100, o["r2026"]]):
            ax.axhline(val, color="red", ls="--", lw=1.2, alpha=0.6,
                       label=f"cb_original ({val:.3f})")

    axes[0].set_ylabel("Calmar"); axes[0].legend(fontsize=8); axes[0].grid(True, alpha=0.25)
    axes[0].set_title(f"v35 Cliff profile — d={d}, q={q}  (halt=0.08)")
    axes[1].set_ylabel("MaxDD (%)"); axes[1].grid(True, alpha=0.25)
    axes[2].set_ylabel("r2026"); axes[2].grid(True, alpha=0.25)
    axes[-1].set_xlabel("CB_WINDOW_DAYS")

    out = PLOT_DIR / "v35_cliff_profile_rank1.png"
    fig.tight_layout(); fig.savefig(out, dpi=170); plt.close(fig)
    return str(out)


# ──────────────────────── Main ────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    print(BAR)
    print("  CRYPTO GODMODE v35 — Top-5 (d,q) × CB transition-zone sweep")
    print("  Locating the MaxDD cliff between cb_original (Calmar=23, 0-2026)")
    print("  and cb_v34_tight (Calmar=17, MaxDD=-35%, r2026=+0.07)")
    print(f"  Top-5: {TOP5}")
    print(f"  CB grid: window∈{CB_WINDOWS}  resume∈{CB_RESUMES}  total={len(CB_CONFIGS)} CB configs")
    print(f"  Total variants: {len(TOP5)} × {len(CB_CONFIGS)} = {len(TOP5)*len(CB_CONFIGS)}")
    print(BAR)

    print("\n[0] Preloading microstructure cache ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        ms = v27._get_ms(sym)
        print(f"  {sym}: {ms.shape}")

    print("\n[1] Building shared market inputs ...")
    df, _      = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask  = np.asarray(df.index >= TEST_START)
    test_ts    = pd.Timestamp(TEST_START)
    factor_R   = build_factor_returns(df)
    w_star     = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned  = build_b_aligned(w_star)
    ohlc_map   = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch         = get_channel_series()
    v27.RT_COST = RT_BPS / 10_000.0

    print("\n[2] Building FFD Sigma and unit signals for top-5 (d,q) ...")
    sigma_store: dict[float, tuple] = {}
    unit_store:  dict[tuple, pd.Series] = {}
    theta_store: dict[tuple, float]     = {}
    d_grid = sorted(set(d for d, q in TOP5))
    for d in d_grid:
        w = ffd_weights(d)
        print(f"  FFD d={d:.2f}: lags={len(w)}")
        Sigma_cap, Sigma_ffd, sdiag, bdiag = build_sigma(factor_R, train_mask, df, d)
        print(f"    cond {sdiag['cond_before']:.2e} → {sdiag['cond_final']:.2f}  "
              f"rho_cap={bdiag['rho_cap']:.4f}")
        sigma_store[d] = (Sigma_cap, Sigma_ffd, sdiag, bdiag)

    for rank_idx, (d, q) in enumerate(TOP5, 1):
        key   = (d, q)
        if key in unit_store:
            continue
        Sigma_cap, _, sdiag, bdiag = sigma_store[d]
        theta = theta_from(b_aligned, train_mask, Sigma_cap, bdiag["budget"], q)
        print(f"  Rank-{rank_idx} d={d:.2f} q={q:.2f}: theta={theta:.5f}", end="")
        log_ann = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned,
                                    Sigma_cap, theta, kappa=KAPPA_A, anneal=True,
                                    label=f"v35_d{d:.2f}_q{q:.2f}")
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

    print(f"\n[3] Sweeping {len(CB_CONFIGS)} CB configs across top-5 ...")
    results:   list[dict]        = []
    sim_store: dict[str, dict]   = {}

    for cb_halt, cb_resume, cb_window, cb_lbl in CB_CONFIGS:
        is_dup = (cb_lbl == "cb_original")  # (w180,r01) already in grid
        for rank_idx, (d, q) in enumerate(TOP5, 1):
            key   = (d, q)
            unit  = unit_store[key]
            theta = theta_store[key]
            _, _, sdiag, bdiag = sigma_store[d]
            sim   = simulate_unit(unit, cb_halt, cb_resume, cb_window)
            ds    = str(d).replace(".", "p")
            qs    = str(q).replace(".", "p")
            label = f"d{ds}_q{qs}_{cb_lbl}"
            r     = result_row(label, sim, test_ts, d, q, cb_lbl,
                               cb_halt, cb_resume, cb_window, theta, sdiag, bdiag)
            results.append(r)
            sim_store[label] = sim
            halted_flag = " [DUP]" if is_dup else ""
            print(f"  R{rank_idx} [{label}]  final=${r['final']:>10,.0f}  "
                  f"Calmar={r['calmar']:+7.3f}  MaxDD={r['maxdd']:+.2%}  "
                  f"halt={r['pct_halted']:.1%}  "
                  f"r2023={r['r2023']:+.4f}  r2024={r['r2024']:+.4f}  "
                  f"r2025={r['r2025']:+.4f}  r2026={r['r2026']:+.4f}{halted_flag}")

    # ── Summary tables ────────────────────────────────────────────────────
    non_dup = [r for r in results if r["cb_label"] != "cb_original"]
    best_calmar = max(results, key=lambda r: r["calmar"])
    best_final  = max(results, key=lambda r: r["final"])

    # Sweet spot: MaxDD > -28% AND r2026 > 0 AND calmar > 15
    sweet = [r for r in non_dup
             if r["maxdd"] > -0.28 and r["r2026"] > 0.0 and r["calmar"] > 15]

    print("\n" + BAR)
    print("  v35 TOP-5 × CB TRANSITION — sorted by Calmar (non-duplicate)")
    print(BAR)
    hdr  = f"  {'Name':<44} R {'d':>4} {'q':>4} {'window':>6} {'resume':>6} "
    hdr += f"{'Final_k':>8} {'Calmar':>7} {'MaxDD%':>7} "
    hdr += f"{'r2025':>7} {'r2026':>7} {'halt%':>6}"
    print(hdr)
    print("  " + "-" * 122)
    for r in sorted(non_dup, key=lambda x: -x["calmar"])[:30]:
        print(f"  {r['name']:<44} {r['rank']} {r['d']:>4.2f} {r['q']:>4.2f} "
              f"{r['cb_window_days']:>6} {r['cb_resume']:>6.2f} "
              f"{r['final']/1000:>8.1f} {r['calmar']:>7.2f} {r['maxdd']*100:>7.2f} "
              f"{r['r2025']:>7.4f} {r['r2026']:>7.4f} {r['pct_halted']*100:>6.1f}")

    print(f"\n  ★ Best Calmar : {best_calmar['name']}  "
          f"final=${best_calmar['final']:,.0f}  Calmar={best_calmar['calmar']:+.3f}  "
          f"MaxDD={best_calmar['maxdd']:+.2%}  r2026={best_calmar['r2026']:+.4f}")
    print(f"  ★ Best Final  : {best_final['name']}  "
          f"final=${best_final['final']:,.0f}  Calmar={best_final['calmar']:+.3f}  "
          f"r2026={best_final['r2026']:+.4f}")

    if sweet:
        print(f"\n  Sweet-spot candidates (MaxDD>-28%, r2026>0, Calmar>15): {len(sweet)}")
        for r in sorted(sweet, key=lambda x: -x["calmar"]):
            print(f"    {r['name']:<44}  Calmar={r['calmar']:.2f}  "
                  f"MaxDD={r['maxdd']*100:.1f}%  r2026={r['r2026']:+.4f}  "
                  f"final=${r['final']:,.0f}")
    else:
        print("\n  No sweet-spot candidates found (MaxDD>-28%, r2026>0, Calmar>15). "
              "Cliff is sharp.")

    # Best new CB per rank
    best_per_rank: list[dict] = []
    print("\n  Best new CB config per rank:")
    for rank_idx, (d, q) in enumerate(TOP5, 1):
        sub = [r for r in non_dup if r["d"] == d and r["q"] == q]
        best = max(sub, key=lambda r: r["calmar"]) if sub else {}
        best_per_rank.append(best)
        if best:
            print(f"   Rank-{rank_idx} d={d} q={q}: {best['cb_label']:<14}  "
                  f"window={best['cb_window_days']}  resume={best['cb_resume']:.2f}  "
                  f"Calmar={best['calmar']:.2f}  MaxDD={best['maxdd']*100:.1f}%  "
                  f"r2026={best['r2026']:+.4f}  final=${best['final']:,.0f}")

    print("\n[4] Generating plots ...")
    p_surfaces = plot_calmar_surface(results)
    for p in p_surfaces:
        print(f"  calmar surface: {p}")
    p_r26 = plot_r2026_surface(results)
    for p in p_r26:
        print(f"  r2026 surface: {p}")
    p_eq = plot_equity_curves_top5(sim_store, best_per_rank, test_ts)
    print(f"  equity curves: {p_eq}")
    p_cliff = plot_cliff_profile(results)
    print(f"  cliff profile: {p_cliff}")

    # ── Save JSON ─────────────────────────────────────────────────────────
    out = OUT_DIR_ / "crypto_godmode_v35_top5_cb_transition.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dict(
            meta=dict(
                version="v35_top5_cb_transition",
                description=(
                    "Top-5 (d,q) from v34 × CB window/resume transition grid. "
                    "Maps the MaxDD cliff between cb_original (Calmar=23, r2026=0) "
                    "and cb_v34_tight (Calmar=17, MaxDD=-35%)."
                ),
                top5_variants=[{"rank": i+1, "d": d, "q": q}
                                for i, (d, q) in enumerate(TOP5)],
                cb_windows=CB_WINDOWS, cb_resumes=CB_RESUMES,
                n_cb_configs=len(CB_CONFIGS), n_variants=len(results),
                v34_references=dict(
                    cb_original=dict(calmar=23.0, maxdd=-0.1526, final=158951, r2026=0.0),
                    cb_v34_tight=dict(calmar=17.5, maxdd=-0.3485, final=730056, r2026=0.066),
                ),
                kappa_cap=KAPPA_CAP, ffd_threshold=FFD_THRESHOLD,
                k=K_NORMAL, rt_bps=RT_BPS,
                elapsed=time.time() - t0,
            ),
            sweet_spot_candidates=sweet,
            best_calmar=best_calmar,
            best_final=best_final,
            results=results,
        ), f, indent=2, default=float)
    print(f"\n  Saved → {out}")
    print(f"  Elapsed: {time.time() - t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()
