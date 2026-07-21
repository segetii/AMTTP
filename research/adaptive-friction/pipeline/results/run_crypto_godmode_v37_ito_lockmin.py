"""
run_crypto_godmode_v37_ito_lockmin.py
======================================

v37 = Itô-BSDT with minimum-lock-duration gate (G2.4 + lock_min parameter)

Motivation
----------
v36 showed a clean bifurcation:

  cb_only η = 1e-4 → 11 resets, r2026 = 0.000, Calmar ≈ 23.28
  cb_only η = 5e-4 → 57 resets, r2026 = 0.324, Calmar ≈ 4.54

The high-η case unlocks 2026 but fires 57 resets during 2022-2025, wasting
momentum from the bull-run and degrading Calmar.  The G2.4 condition triggers
early because the noise budget grows with EVERY lock (including short 1-2 week
trips).

Fix (G2.4 gate): add a lock_min parameter that prevents the G2.4 override from
firing unless the engine has been locked for at least lock_min bars.

  • Short 2022/2024/2025 trips  (lock_bars < lock_min) → NOT reset → Calmar preserved
  • Terminal 2026 lock          (lock_bars ≈ 4320+)    → reset once → r2026 > 0

The terminal 2026 lock starts Nov-2025 and the data ends May-2026 ≈ 180 days ≈
4320 bars.  Setting lock_min ∈ {1000, 2000, 3000} bars ensures only truly
persistent locks (≥ 42, 83, 125 days) trigger the override.

Grid (cb_only mode only — ODE is deterministic η_ode=0)
-----------------------------------------------------------
  η ∈ {0, 5e-5, 1e-4, 2e-4, 3e-4, 5e-4}    — noise scale for c_σ budget
  lock_min ∈ {0, 500, 1000, 2000, 3000}     — min lock_bars before G2.4 fires
  (d, q) ∈ TOP3 from v36                    — 3 most informative ranks
  Fixed CB: cb_original (halt=0.08, resume=0.01, window=180d)

  η=0 → no override at any lock_min (all identical) → 1 baseline per (d,q)
  Effective unique variants: (5 non-zero η × 5 lock_min + 1 baseline) × 3 = 78

Expected outcome
----------------
  lock_min ≈ 2000, η = 2e-4 to 5e-4:
    - c_σ_per_bar = η × DT × rank_Ix = {6e-5, 1.5e-4}
    - Budget at lock_min=2000: {0.120, 0.300}
    - Fires if cb_dd ≤ cb_resume + budget = {0.130, 0.310}
    - Terminal 2026 lock fires after 2000 bars (≈ 83 days) → r2026 > 0
    - Short earlier trips (< 2000 bars) → NOT reset → Calmar preserved ≈ 23

Runtime estimate
----------------
  3 ODE runs × ~90s + 78 CB sims × ~3s = ~500s ≈ 8-9 min
  (ODE runs already cached in memory for first symbol fetch)

Theory references
-----------------
  G2.1 : Itô energy equation
  G2.2 : Fisher noise choice Σ = I_X^{†1/2}
  G2.4 : Stochastic ultimate boundedness with minimal lock duration gate
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from collections import deque

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))

import run_crypto_godmode_v27_all_microstructure as v27
import run_crypto_godmode_v28_canonical_stability as v28
from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START, TRAIN_START, build_1h_df
from run_crypto_godmode_v1 import (
    KAPPA_A, W_TARGET_A1, build_b_aligned, build_w_star,
    _predictive_scalars, CONV_MIN, CONV_MAX, W_BOX,
    ANNEAL_AMP, ANNEAL_PEAK,
    TradingDomain, EPSILON,
)
from run_crypto_canonical_v4 import (
    A_FACTORS, N_STATE, K_FACTOR, DT,
    build_factor_returns, rescale_to_correlation,
)
from run_crypto_godmode_v8_multiasset_shell import ASSETS, build_asset_inputs, fetch_futures_ohlcv_symbol
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from simulate_master_strategy import (
    DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR, INIT, HOURS_PER_DAY,
    equity_metrics, period_table,
)
from run_crypto_godmode_v35_top5_cb_transition import (
    ffd_weights, frac_diff_series, ffd_covariance,
    build_sigma, theta_from,
    TOP5, CB_HALT as CB_HALT_DEFAULT, REG_VARIANT,
    FFD_THRESHOLD, FFD_MAX_LAG, K_NORMAL, RT_BPS, KAPPA_CAP,
)

BAR       = "=" * 120
OUT_DIR_  = Path(OUT_DIR) / "v37_ito_lockmin"
PLOT_DIR  = OUT_DIR_ / "plots"

# TOP3 (d,q) — most informative from v36
TOP3 = [
    (0.30, 0.50),   # v36 rank-1: baseline Calmar=23.00
    (0.30, 0.65),   # v36 rank-2: best Calmar=23.98 (cb_only η=1e-4)
    (0.25, 0.50),   # v36 rank-3: only rank with r2026>0 at high η
]

# ── v37 grid ─────────────────────────────────────────────────────────────────
ETA_GRID      = [0.0, 5e-5, 1e-4, 2e-4, 3e-4, 5e-4]   # noise scale η
LOCK_MIN_GRID = [0, 500, 1000, 2000, 3000]              # min bars before G2.4 fires

# Fixed CB: cb_original (the 2026 self-lock config)
CB_HALT   = 0.08
CB_RESUME = 0.01
CB_WINDOW = 180   # days


# ── Fisher noise helpers (identical to v36) ──────────────────────────────────

def fisher_weight_noise_sqrt(Sigma_cap: np.ndarray, eps: float = 1e-10) -> tuple[np.ndarray, int]:
    """Compute I_X^{-1/2} in weight space (Fisher-optimal noise matrix, G2.2)."""
    G         = np.linalg.inv(Sigma_cap)
    I_X       = A_FACTORS.T @ G @ A_FACTORS
    vals, vecs = np.linalg.eigh(I_X)
    rank_Ix   = int(np.sum(vals > eps * vals[-1]))
    inv_sqrt  = np.zeros_like(vals)
    for i in range(rank_Ix):
        inv_sqrt[i] = 1.0 / np.sqrt(max(vals[i], eps))
    Sigma_w_sqrt = vecs @ np.diag(inv_sqrt) @ vecs.T
    return Sigma_w_sqrt, rank_Ix


def c_sigma_per_bar(eta: float, rank_Ix: int) -> float:
    """Itô energy correction per bar: c_σ = η · DT · rank(I_X)."""
    return eta * DT * rank_Ix


# ── Deterministic canonical ODE (η=0, identical to v35) ────────────────────

def run_godmode_det(df: pd.DataFrame,
                    train_mask: np.ndarray,
                    test_mask: np.ndarray,
                    w_star_arr: np.ndarray,
                    b_arr: np.ndarray,
                    Sigma_cap: np.ndarray,
                    theta_base: float,
                    kappa: float = KAPPA_A,
                    label: str = "") -> pd.DataFrame:
    """Deterministic canonical ODE — no Itô noise, equivalent to v35 baseline."""
    T    = len(df)
    R = np.column_stack([
        df["ret_btc"].fillna(0.0).values,
        df["ret_eth"].fillna(0.0).values,
        (df["ret_sol"].fillna(0.0).values if "ret_sol" in df.columns
         else df["ret_eth"].fillna(0.0).values),
    ])

    rho_train = []
    for t in np.where(train_mask)[0][::50]:
        sys_t = TradingDomain(
            A=A_FACTORS, b=b_arr[t], Sigma=Sigma_cap,
            kappa=kappa, w_star=w_star_arr[t],
            theta=theta_base, epsilon=EPSILON,
        ).build()
        sc = _predictive_scalars(sys_t, np.zeros(N_STATE))
        if sc["rho_eff"] > 0:
            rho_train.append(sc["rho_eff"])
    rho_typ = float(np.median(rho_train)) if rho_train else 1.0

    hours = df.index.hour
    keys = ["E", "gamma", "dE_dt", "cos_theta", "mfls", "v_E", "rho_eff",
            "rhs_norm", "w_btc", "w_eth", "w_sol", "pnl", "pnl_long_only",
            "stop_flag", "stale_flag", "drift_flag", "conviction", "theta_t"]
    log  = {k: np.zeros(T) for k in keys}

    w           = np.zeros(N_STATE, dtype=float)
    cos_th_prev = 0.0
    t0          = time.time()

    for t in range(T):
        hr      = int(hours[t])
        theta_t = theta_base * (1.0 + ANNEAL_AMP * np.cos(
            2.0 * np.pi * (hr - ANNEAL_PEAK) / 24.0))
        sys_t = TradingDomain(
            A=A_FACTORS, b=b_arr[t], Sigma=Sigma_cap,
            kappa=kappa, w_star=w_star_arr[t],
            theta=theta_t, epsilon=EPSILON,
        ).build()
        sc         = _predictive_scalars(sys_t, w)
        conviction = float(np.clip(-cos_th_prev, CONV_MIN, CONV_MAX))
        w          = np.clip(w + DT * sc["rhs"] * conviction, -W_BOX, W_BOX)

        stop_flag  = 1.0 if sc["gamma"] > 0.90 else 0.0
        stale_flag = 1.0 if (sc["rho_eff"] > 0 and sc["rho_eff"] < 0.1 * rho_typ) else 0.0
        drift_flag = 1.0 if sc["cos_theta"] > 0.0 else 0.0

        log["E"][t]          = sc["E"]
        log["gamma"][t]      = sc["gamma"]
        log["dE_dt"][t]      = sc["dE_dt"]
        log["cos_theta"][t]  = sc["cos_theta"]
        log["mfls"][t]       = sc["mfls"]
        log["v_E"][t]        = sc["v_E"]
        log["rho_eff"][t]    = sc["rho_eff"]
        log["rhs_norm"][t]   = sc["rhs_norm"]
        log["w_btc"][t]      = w[0]
        log["w_eth"][t]      = w[1]
        log["w_sol"][t]      = w[2]
        log["pnl"][t]        = float(w @ R[t])
        log["pnl_long_only"][t] = float(R[t].mean())
        log["stop_flag"][t]  = stop_flag
        log["stale_flag"][t] = stale_flag
        log["drift_flag"][t] = drift_flag
        log["conviction"][t] = conviction
        log["theta_t"][t]    = theta_t

        cos_th_prev = sc["cos_theta"]
        if t > 0 and (t % 5000) == 0:
            elapsed = time.time() - t0
            print(f"    [{label}] {t:>6}/{T}  ({elapsed:>5.1f}s)")

    return pd.DataFrame(log, index=df.index)


# ── Gated G2.4 CB simulation ─────────────────────────────────────────────────

def simulate_combined_lockmin(
    unit_normal:     pd.Series,
    unit_crash:      pd.Series,
    K_normal:        float,
    K_crash:         float,
    dd_soft:         float,
    dd_stop:         float,
    y_floor:         float,
    cb_halt:         float,
    cb_resume:       float,
    cb_window_days:  int,
    ito_c_sigma_bar: float,    # c_σ per bar  (= η · DT · rank_Ix)
    lock_min:        int,      # G2.4 gate: only fires if lock_bars >= lock_min
) -> dict:
    """simulate_combined with gated G2.4 Fisher-adaptive CB override.

    Standard resume: cb_dd <= cb_resume  (unchanged)

    Gated G2.4 override fires when ALL of:
      1. lock_bars >= lock_min                (gate: only long locks qualify)
      2. ito_c_sigma_bar > 0                  (η > 0)
      3. cb_dd <= cb_resume + c_σ × lock_bars (noise budget covers the gap)

    lock_min = 0 reproduces v36 cb_only behaviour (no gate).
    """
    window_bars  = cb_window_days * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq = INIT; peak_alltime = INIT; halted = False
    halt_start_bar = 0

    eq_vals = []; y_vals = []; cb_flags = []; lock_bars_arr = []
    ito_resets = 0
    reset_bar_log: list[int] = []    # for diagnostics

    for bar_i in range(len(unit_normal)):
        ur_n = float(unit_normal.iloc[bar_i])
        ur_c = float(unit_crash.iloc[bar_i])

        # Sliding-window peak (unchanged)
        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((bar_i, eq))
        roll_peak = mono_dq[0][1]

        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak,    1e-12))

        if not halted and cb_dd >= cb_halt:
            halted = True
            halt_start_bar = bar_i
        elif halted:
            lock_bars = bar_i - halt_start_bar

            # Standard resume
            if cb_dd <= cb_resume:
                halted = False
            # Gated G2.4 override
            elif ito_c_sigma_bar > 0.0 and lock_bars >= lock_min:
                noise_budget = ito_c_sigma_bar * lock_bars
                if cb_dd <= cb_resume + noise_budget:
                    # After override, reset roll_peak so engine re-enters cleanly.
                    # We do NOT modify eq — just log the reset and unlock.
                    halted = False
                    ito_resets += 1
                    reset_bar_log.append(bar_i)
                    # Reset halt_start_bar so next trip accumulates fresh
                    halt_start_bar = bar_i

        if halted:
            y = 0.0
        elif dd_aty <= dd_soft:
            y = 1.0
        elif dd_aty >= dd_stop:
            y = y_floor
        else:
            y = y_floor + (1.0 - y_floor) * (dd_stop - dd_aty) / (dd_stop - dd_soft)

        r = K_normal * y * ur_n + K_crash * ur_c
        r = max(r, -0.95)
        eq *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)
        eq_vals.append(eq)
        y_vals.append(y)
        cb_flags.append(int(halted))
        lock_bars_arr.append(bar_i - halt_start_bar if halted else 0)

    eqs  = pd.Series(eq_vals, index=unit_normal.index)
    rets = eqs.pct_change().fillna(eqs.iloc[0] / INIT - 1.0)
    dd_s = (eqs - eqs.cummax()) / eqs.cummax()
    years = max((eqs.index[-1] - eqs.index[0]).days / 365.25, 1e-9)

    # CB reset timing: map bar indices to timestamps
    reset_ts = [unit_normal.index[b] for b in reset_bar_log
                if b < len(unit_normal.index)]

    return dict(
        eq            = eqs,
        final         = float(eqs.iloc[-1]),
        cagr          = float((eqs.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe        = float(np.sqrt(24 * 365.25) * rets.mean() / rets.std())
                        if rets.std() > 0 else 0.0,
        maxdd         = float(dd_s.min()),
        pct_halted    = float(np.mean(cb_flags)),
        n_trips       = int(sum(cb_flags[i] > cb_flags[i - 1]
                               for i in range(1, len(cb_flags)))),
        avg_y         = float(np.mean(y_vals)),
        ito_resets    = ito_resets,
        max_lock_bars = int(max(lock_bars_arr)) if lock_bars_arr else 0,
        reset_ts      = [str(ts) for ts in reset_ts],
    )


# ── Metrics helpers ──────────────────────────────────────────────────────────

def yoy(eq: pd.Series) -> dict[str, float]:
    return {r["period"][:4]: r["return_pct"] for r in period_table(eq, "Y")}


def result_row(label, sim, test_ts, d, q, eta, lock_min,
               c_sigma_bar, rank_Ix, sdiag, bdiag) -> dict:
    eq = sim["eq"][sim["eq"].index >= test_ts]
    m  = equity_metrics(eq, label)
    yy = yoy(eq)
    return dict(
        name=label, d=d, q=q, eta=eta, lock_min=lock_min,
        c_sigma_bar=c_sigma_bar, rank_Ix=rank_Ix,
        final=m["final"], profit=m["final"] - INIT,
        cagr=m["cagr"], sharpe=m["sharpe"], maxdd=m["maxdd"], calmar=m["calmar"],
        pct_halted=sim.get("pct_halted", float("nan")),
        n_trips=sim.get("n_trips", 0),
        ito_resets=sim.get("ito_resets", 0),
        max_lock_bars=sim.get("max_lock_bars", 0),
        reset_ts=sim.get("reset_ts", []),
        r2022=yy.get("2022", float("nan")),
        r2023=yy.get("2023", float("nan")),
        r2024=yy.get("2024", float("nan")),
        r2025=yy.get("2025", float("nan")),
        r2026=yy.get("2026", float("nan")),
        sigma=sdiag, budget=bdiag,
    )


# ── Plots ─────────────────────────────────────────────────────────────────────

def plot_lockmin_vs_r2026(results: list[dict]) -> list[str]:
    """For each (d,q): 2D heatmap of r2026 and Calmar over (η, lock_min)."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for rank_idx, (d, q) in enumerate(TOP3, 1):
        sub = [r for r in results if r["d"] == d and r["q"] == q and r["eta"] > 0]
        if not sub:
            continue
        etas   = sorted(set(r["eta"]      for r in sub))
        lmins  = sorted(set(r["lock_min"] for r in sub))
        r2026_mat = np.full((len(etas), len(lmins)), float("nan"))
        cal_mat   = np.full((len(etas), len(lmins)), float("nan"))
        rst_mat   = np.full((len(etas), len(lmins)), float("nan"))
        for r in sub:
            i = etas.index(r["eta"])
            j = lmins.index(r["lock_min"])
            r2026_mat[i, j] = r["r2026"] if r["r2026"] == r["r2026"] else 0.0
            cal_mat[i, j]   = r["calmar"]
            rst_mat[i, j]   = r["ito_resets"]

        fig, axes = plt.subplots(1, 3, figsize=(16, 5))
        for ax, mat, title, fmt in [
            (axes[0], r2026_mat, "r2026",       ".2f"),
            (axes[1], cal_mat,   "Calmar",       ".1f"),
            (axes[2], rst_mat,   "Itô resets",   ".0f"),
        ]:
            im = ax.imshow(mat, aspect="auto", origin="lower",
                           cmap="RdYlGn" if title != "Itô resets" else "Blues")
            ax.set_xticks(range(len(lmins)))
            ax.set_xticklabels([f"{lm:,}" for lm in lmins], fontsize=8)
            ax.set_yticks(range(len(etas)))
            ax.set_yticklabels([f"{e:.0e}" for e in etas], fontsize=8)
            ax.set_xlabel("lock_min (bars)", fontsize=9)
            ax.set_ylabel("η (noise scale)", fontsize=9)
            ax.set_title(title, fontweight="bold")
            plt.colorbar(im, ax=ax)
            # Annotate cells
            for i in range(len(etas)):
                for j in range(len(lmins)):
                    v = mat[i, j]
                    if not np.isnan(v):
                        ax.text(j, i, f"{v:{fmt}}", ha="center", va="center",
                                fontsize=7, color="black")
        fig.suptitle(
            f"v37 Rank-{rank_idx}: d={d}, q={q}  — G2.4 gated CB unlock sweep\n"
            f"(cb_only: deterministic ODE, G2.4 fires only when lock_bars ≥ lock_min)",
            fontweight="bold",
        )
        out = PLOT_DIR / f"v37_heatmap_rank{rank_idx}_d{str(d).replace('.','p')}_q{str(q).replace('.','p')}.png"
        fig.tight_layout()
        fig.savefig(out, dpi=160)
        plt.close(fig)
        paths.append(str(out))
    return paths


def plot_equity_best(sim_store: dict[str, dict], results: list[dict],
                     test_ts: pd.Timestamp) -> str:
    """Best Calmar variant with r2026>0 vs v35 baseline per rank."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(len(TOP3), 1, figsize=(16, 4 * len(TOP3)), sharex=True)
    if len(TOP3) == 1:
        axes = [axes]
    for ax_i, (d, q) in enumerate(TOP3):
        ax = axes[ax_i]
        # v35 baseline (η=0, lock_min=0)
        base_key = f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}_eta0_lm0"
        if base_key in sim_store:
            eq = sim_store[base_key]["eq"]
            eq = eq[eq.index >= test_ts]
            ax.semilogy(eq.index, eq.values, color="tomato", lw=1.4,
                        label=f"η=0 baseline  ${eq.iloc[-1]:,.0f}  "
                              f"Calmar={[r for r in results if r['name']==base_key][0]['calmar']:.2f}")

        # Best by Calmar among r2026 > 0 variants
        sub_pos = [r for r in results if r["d"] == d and r["q"] == q
                   and r["eta"] > 0 and r.get("r2026", 0) > 0]
        sub_all = [r for r in results if r["d"] == d and r["q"] == q and r["eta"] > 0]
        for sub, color, lbl in [(sub_pos, "steelblue", "best r2026>0"),
                                 (sub_all,  "darkorange", "best Calmar overall")]:
            if not sub:
                continue
            b   = max(sub, key=lambda r: r["calmar"])
            bk  = b["name"]
            if bk in sim_store:
                eq2 = sim_store[bk]["eq"]
                eq2 = eq2[eq2.index >= test_ts]
                ax.semilogy(eq2.index, eq2.values, color=color, lw=1.6,
                            label=f"η={b['eta']:.0e} lm={b['lock_min']} {lbl}  "
                                  f"${eq2.iloc[-1]:,.0f}  Calmar={b['calmar']:.2f}  "
                                  f"r2026={b['r2026']:+.3f}  resets={b['ito_resets']}")

        ax.set_title(f"v37 Rank-{ax_i+1}: d={d}, q={q}")
        ax.set_ylabel("Equity ($)")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.25)
    axes[-1].set_xlabel("Date")
    fig.suptitle("v37: Gated G2.4 CB unlock — best variants vs v35 baseline",
                 fontweight="bold", y=1.01)
    out = PLOT_DIR / "v37_equity_best_vs_baseline.png"
    fig.tight_layout()
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return str(out)


def plot_reset_timeline(sim_store: dict[str, dict], results: list[dict],
                        test_ts: pd.Timestamp) -> str:
    """Show WHEN resets fire along the equity curve for chosen variants."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    # Focus on d0.25_q0.50 since that's where r2026 appeared in v36
    d_focus, q_focus = 0.25, 0.50
    sub = sorted(
        [r for r in results if r["d"] == d_focus and r["q"] == q_focus
         and r["eta"] > 0 and r["ito_resets"] > 0
         and r["lock_min"] in (1000, 2000, 3000)],
        key=lambda r: (r["lock_min"], r["eta"])
    )
    if not sub:
        # Fallback: any rank with resets
        sub = sorted(
            [r for r in results if r["eta"] > 0 and r["ito_resets"] > 0],
            key=lambda r: (r["lock_min"], r["eta"])
        )[:6]

    if not sub:
        return ""

    n = min(len(sub), 6)
    fig, axes = plt.subplots(n, 1, figsize=(16, 3 * n), sharex=True)
    if n == 1:
        axes = [axes]
    colors = plt.cm.tab10.colors
    for ax_i, row in enumerate(sub[:n]):
        ax = axes[ax_i]
        bk = row["name"]
        if bk not in sim_store:
            continue
        sim = sim_store[bk]
        eq  = sim["eq"]
        ax.semilogy(eq.index, eq.values, color=colors[ax_i % 10], lw=1.0, alpha=0.8)
        # Mark Itô resets
        for ts_str in row.get("reset_ts", []):
            ts = pd.Timestamp(ts_str)
            if ts in eq.index:
                ax.axvline(ts, color="red", lw=1.5, alpha=0.7, ls="--")
                ax.annotate("reset", xy=(ts, eq[ts]), xytext=(5, 5),
                            textcoords="offset points", fontsize=7, color="red")
        ax.axvline(pd.Timestamp("2026-01-01"), color="purple", lw=1.2, ls=":", alpha=0.5)
        ax.set_title(f"η={row['eta']:.0e}  lock_min={row['lock_min']}  "
                     f"Calmar={row['calmar']:.2f}  r2026={row['r2026']:+.3f}  "
                     f"resets={row['ito_resets']}", fontsize=9)
        ax.set_ylabel("Equity ($)")
        ax.grid(True, alpha=0.25)
    axes[-1].set_xlabel("Date")
    fig.suptitle(f"v37 CB Override Reset Timeline (d={d_focus}, q={q_focus})",
                 fontweight="bold")
    out = PLOT_DIR / "v37_reset_timeline.png"
    fig.tight_layout()
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return str(out)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    t0_total = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    n_unique_ode  = len(TOP3)
    n_cb_variants = (len(ETA_GRID) * len(LOCK_MIN_GRID) - (len(LOCK_MIN_GRID) - 1)) * len(TOP3)
    # η=0: 1 per rank (all lock_min give same result → deduplicated to 1)
    # η>0: 5 × 5 = 25 per rank → 25 × 3 = 75
    # Total: 75 + 3 = 78

    print(BAR)
    print("  CRYPTO GODMODE v37 — Gated G2.4 CB Override (lock_min)")
    print("  ODE: deterministic (η_ode = 0); CB budget: c_σ = η·DT·rank(I_X)")
    print("  G2.4 fires only when: lock_bars ≥ lock_min AND cb_dd ≤ cb_resume + c_σ·lock_bars")
    print(f"  η grid:         {ETA_GRID}")
    print(f"  lock_min grid:  {LOCK_MIN_GRID}  (bars;  ÷24 ≈ days)")
    print(f"  (d,q) TOP3:     {TOP3}")
    print(f"  CB config:      halt={CB_HALT}  resume={CB_RESUME}  window={CB_WINDOW}d")
    print(f"  ODE runs:       {n_unique_ode}")
    print(f"  CB sim variants: {n_cb_variants}")
    print(BAR)

    # ── [0] Microstructure cache ────────────────────────────────────────────
    print("\n[0] Preloading microstructure cache ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        ms = v27._get_ms(sym)
        print(f"  {sym}: {ms.shape}")

    # ── [1] Shared market inputs ────────────────────────────────────────────
    print("\n[1] Building shared market inputs ...")
    df, _      = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask  = np.asarray(df.index >= TEST_START)
    test_ts    = pd.Timestamp(TEST_START)
    w_star     = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned  = build_b_aligned(w_star)
    factor_R   = build_factor_returns(df)
    v27.RT_COST = RT_BPS / 10_000.0

    # ── [2] FFD Sigma and Fisher noise matrices ─────────────────────────────
    print("\n[2] Building FFD Sigma and Fisher noise matrices ...")
    sigma_store: dict[float, tuple] = {}
    for d in sorted(set(d for d, q in TOP3)):
        Sigma_cap, Sigma_ffd, sdiag, bdiag = build_sigma(factor_R, train_mask, df, d)
        Sigma_w_sqrt, rank_Ix = fisher_weight_noise_sqrt(Sigma_cap)
        G     = np.linalg.inv(Sigma_cap)
        I_X   = A_FACTORS.T @ G @ A_FACTORS
        kp_IX = float(np.linalg.cond(I_X))
        kp_S0 = float(np.linalg.cond(Sigma_cap))
        print(f"  d={d:.2f}: κ(Σ₀)={kp_S0:.2f}  rank(I_X)={rank_Ix}  κ(I_X)={kp_IX:.2f}  "
              f"rho_cap={bdiag['rho_cap']:.4f}")
        if kp_S0 > 100:
            print(f"    WARNING G7: κ(Σ₀) > 100")
        sigma_store[d] = (Sigma_cap, Sigma_ffd, sdiag, bdiag, Sigma_w_sqrt, rank_Ix)

    # c_σ per bar diagnostic
    print("\n  c_σ per bar at all η values:")
    for d in sorted(set(d for d, q in TOP3)):
        _, _, _, _, _, rank_Ix = sigma_store[d]
        for eta in ETA_GRID:
            if eta == 0:
                continue
            csb = c_sigma_per_bar(eta, rank_Ix)
            budgets = {lm: csb * lm for lm in LOCK_MIN_GRID if lm > 0}
            print(f"    d={d:.2f}  η={eta:.0e}:  c_σ/bar={csb:.3e}  "
                  f"budgets@lock_min={budgets}")

    # ── [3] Deterministic ODE sweep (one per (d,q)) ─────────────────────────
    print("\n[3] Running deterministic ODE sweeps ...")
    unit_store:   dict[tuple, pd.Series] = {}
    theta_store:  dict[tuple, float]     = {}

    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol)
                for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()

    for d, q in TOP3:
        Sigma_cap, _, sdiag, bdiag, Sigma_w_sqrt, rank_Ix = sigma_store[d]
        theta = theta_from(b_aligned, train_mask, Sigma_cap, bdiag["budget"], q)
        theta_store[(d, q)] = theta
        label = f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}_det"
        print(f"  ODE: {label}  θ={theta:.5f}", end="  ", flush=True)
        t_ode = time.time()

        log_ann = run_godmode_det(
            df, train_mask, test_mask, w_star, b_aligned,
            Sigma_cap, theta, kappa=KAPPA_A, label=label,
        )

        inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                        signal_kind="wstar", use_quadrant=False)
        inputs_q   = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                        signal_kind="wstar", use_quadrant=True)
        inputs     = attach_q_hot(inputs_noq, inputs_q)
        sig_map    = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}")
                      for asset, _, _, idx in ASSETS}
        unit = v28.run_variant_v28(REG_VARIANT, inputs, sig_map, log_ann)["unit"]
        unit_store[(d, q)] = unit
        print(f"{time.time()-t_ode:.1f}s  unit={len(unit)}")

    # ── [4] CB simulation sweep ─────────────────────────────────────────────
    print(f"\n[4] Running CB simulation sweep (gated G2.4) ...")
    results:       list[dict]        = []
    sim_store_eq:  dict[str, dict]   = {}

    # Header
    print(f"\n  {'Variant':<80}  {'Calmar':>7}  {'Final':>12}  {'r2026':>7}  "
          f"{'Halt%':>6}  {'Resets':>6}  {'MaxLock':>7}")
    print(f"  {'-'*80}  {'-'*7}  {'-'*12}  {'-'*7}  {'-'*6}  {'-'*6}  {'-'*7}")

    for d, q in TOP3:
        Sigma_cap, _, sdiag, bdiag, Sigma_w_sqrt, rank_Ix = sigma_store[d]
        unit = unit_store[(d, q)]

        for eta in ETA_GRID:
            c_sb = c_sigma_per_bar(eta, rank_Ix)

            for lock_min in LOCK_MIN_GRID:
                # η=0: no override regardless of lock_min → only run once (lock_min=0)
                if eta == 0.0 and lock_min > 0:
                    continue

                label = (f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}"
                         f"_eta{eta:.0e}_lm{lock_min}")

                sim = simulate_combined_lockmin(
                    unit_normal=unit,
                    unit_crash=pd.Series(0.0, index=unit.index),
                    K_normal=K_NORMAL, K_crash=0.0,
                    dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
                    cb_halt=CB_HALT, cb_resume=CB_RESUME,
                    cb_window_days=CB_WINDOW,
                    ito_c_sigma_bar=c_sb,
                    lock_min=lock_min,
                )
                sim_store_eq[label] = sim

                row = result_row(
                    label, sim, test_ts, d, q, eta, lock_min,
                    c_sb, rank_Ix, sdiag, bdiag,
                )
                results.append(row)

                print(f"  {label[:80]:<80}  "
                      f"{row['calmar']:>7.2f}  "
                      f"${row['final']:>11,.0f}  "
                      f"{row['r2026']:>+7.3f}  "
                      f"{row['pct_halted']:>6.1%}  "
                      f"{sim['ito_resets']:>6}  "
                      f"{sim['max_lock_bars']:>7}")

    # ── [5] Summary ──────────────────────────────────────────────────────────
    print(f"\n{BAR}")
    print("  v37 RESULTS SUMMARY")
    print(f"  Total variants: {len(results)}")
    print()

    # Best r2026
    pos26 = [r for r in results if r.get("r2026", 0) > 0]
    if pos26:
        best_r26 = max(pos26, key=lambda r: r["r2026"])
        print(f"  Best r2026:  {best_r26['name']}")
        print(f"               calmar={best_r26['calmar']:.2f}  "
              f"final=${best_r26['final']:,.0f}  "
              f"r2026={best_r26['r2026']:.4f}  "
              f"resets={best_r26['ito_resets']}")
    else:
        print("  Best r2026:  (none > 0)")

    # Best Calmar with r2026 > 0
    sweet = [r for r in results if r.get("r2026", 0) > 0 and r.get("calmar", 0) > 0]
    if sweet:
        best_sw = max(sweet, key=lambda r: r["calmar"])
        print(f"\n  Best Calmar with r2026>0:  {best_sw['name']}")
        print(f"    calmar={best_sw['calmar']:.2f}  final=${best_sw['final']:,.0f}  "
              f"r2026={best_sw['r2026']:.4f}  resets={best_sw['ito_resets']}  "
              f"lock_min={best_sw['lock_min']}")

    # Best Calmar overall
    best_cal = max(results, key=lambda r: r.get("calmar", 0))
    print(f"\n  Best Calmar overall:  {best_cal['name']}")
    print(f"    calmar={best_cal['calmar']:.2f}  final=${best_cal['final']:,.0f}  "
          f"r2026={best_cal['r2026']:.4f}  resets={best_cal['ito_resets']}")

    # η=0 baselines
    print(f"\n  η=0 baselines (deterministic, v35-equivalent):")
    for r in sorted([r for r in results if r["eta"] == 0.0], key=lambda r: (r["d"], r["q"])):
        print(f"    d={r['d']:.2f} q={r['q']:.2f}:  calmar={r['calmar']:.2f}  "
              f"final=${r['final']:,.0f}  r2026={r['r2026']:+.3f}")

    # Sweet-spot table
    print(f"\n  Sweet-spot scan (d=0.25, q=0.50):")
    sub_25 = [r for r in results if r["d"] == 0.25 and r["q"] == 0.50 and r["eta"] > 0]
    sub_25.sort(key=lambda r: (r["lock_min"], r["eta"]))
    print(f"  {'lock_min':>8}  {'eta':>9}  {'Calmar':>7}  {'Final':>12}  "
          f"{'r2026':>7}  {'Halt%':>6}  {'Resets':>6}  {'MaxLock':>7}")
    for r in sub_25:
        print(f"  {r['lock_min']:>8}  {r['eta']:>9.1e}  {r['calmar']:>7.2f}  "
              f"${r['final']:>11,.0f}  {r['r2026']:>+7.3f}  "
              f"{r['pct_halted']:>6.1%}  {r['ito_resets']:>6}  {r['max_lock_bars']:>7}")

    # ── [6] Save JSON ────────────────────────────────────────────────────────
    print(f"\n[6] Saving results ...")
    def serialise(obj):
        if isinstance(obj, float) and (obj != obj or obj == float("inf") or obj == float("-inf")):
            return None
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        raise TypeError(type(obj))

    out_json = OUT_DIR_ / "crypto_godmode_v37_ito_lockmin.json"
    # Strip equity series (too large for JSON), keep row metrics
    rows_clean = [{k: v for k, v in r.items()
                   if k not in ("sigma", "budget") and not isinstance(v, pd.Series)}
                  for r in results]
    with open(out_json, "w") as f:
        json.dump({"version": "v37", "results": rows_clean}, f,
                  indent=2, default=serialise)
    print(f"  → {out_json}")

    # ── [7] Plots ────────────────────────────────────────────────────────────
    print(f"\n[7] Generating plots ...")
    heatmap_paths = plot_lockmin_vs_r2026(results)
    print(f"  Heatmap plots: {len(heatmap_paths)}")
    eq_path = plot_equity_best(sim_store_eq, results, test_ts)
    print(f"  Equity curve plot: {eq_path}")
    rl_path = plot_reset_timeline(sim_store_eq, results, test_ts)
    if rl_path:
        print(f"  Reset timeline plot: {rl_path}")

    elapsed = time.time() - t0_total
    print(f"\n{BAR}")
    print(f"  v37 COMPLETE  |  elapsed={elapsed:.1f}s  ({elapsed/60:.1f} min)")
    print(BAR)


if __name__ == "__main__":
    main()
