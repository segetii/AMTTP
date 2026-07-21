"""
run_crypto_godmode_v36_ito_bsdt.py
====================================

v36 = Itô-BSDT: Real Stochastic Extension + Fisher-Adaptive CB

Motivation
----------
v35 confirmed that the 91.5% halt rate with CB_WINDOW=180 fully locks the engine
out of 2026 (r2026=0.0) — the Nov-2025 burst sets a roll-peak that isn't
recovered within the remaining data.

Two approaches to fix this are tested via canonical_v4_gap_closure.md Section G2:

1. REAL ITÔ NOISE on the canonical ODE (G2.1)
   dw = H(w)dt + Σ(w)dW_t
   where H(w) is the existing drift and Σ(w) = sqrt(η) · I_X^{-1/2} is
   Fisher-optimal (G2.2).  The noise is in weight space, scaled so
   the long-run energy increment from the Itô correction is:
     c_σ per bar = η · DT · rank(I_X)   (from G2.1 Itô equation)

2. FISHER-ADAPTIVE CB OVERRIDE (G2.4 Stochastic Ultimate Boundedness)
   Theorem G2.4 says that under the stochastic system, the admissibility
   threshold becomes Ψ*_eff = Ψ* + c_σ.  Translated to the CB:
   the "effective resume band" grows by the accumulated Itô budget:
     noise_budget(t) = c_σ_per_bar × lock_bars
   When cb_dd ≤ cb_resume + noise_budget, the engine unlocks because the
   remaining drawdown gap is within the stochastic energy corridor.

Single η parameter controls both:  η → ODE noise scale AND c_σ for CB.

Grid
----
  η ∈ {0, 1e-5, 5e-5, 1e-4, 5e-4}       — 5 noise levels (0 = v35 baseline)
  (d, q) = Top-5 from v35                 — same as v35
  CB: cb_original (w=180, halt=0.08, resume=0.01) — the self-locking config
  Ablation:
    ito_mode ∈ {'full', 'cb_only', 'ode_only'}
      'full'     — ODE noise + CB override (canonical SDE, η drives both)
      'cb_only'  — CB override only  (η_ode=0, c_σ from η)
      'ode_only' — ODE noise only    (no CB override)
    cb_only isolates G2.4; ode_only tests whether ODE noise alone solves 2026.

Total: 5 η × 5 (d,q) × 3 modes = 75 variants
  (η=0 is the same for all modes → 15 baselines deduplicated = 65 unique runs)
Expected runtime: ~700-900s

Theory references
-----------------
  G2.1 : Itô energy equation
  G2.2 : Fisher noise choice Σ = I_X^{†1/2}, chart-independent Itô correction
  G2.3 : Free-energy identification (Ė_ε ≤ 0 analogue)
  G2.4 : Stochastic ultimate boundedness — M_eff = M + c_σ
  G7   : Admissibility vs κ(Σ₀) — calibration conditioning
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
import run_crypto_godmode_v30_fractional_ricci as v30
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

BAR      = "=" * 120
OUT_DIR_ = Path(OUT_DIR) / "v36_ito_bsdt"
PLOT_DIR = OUT_DIR_ / "plots"

# ── Itô noise grid ──────────────────────────────────────────────────────────
ETA_GRID   = [0.0, 1e-5, 5e-5, 1e-4, 5e-4]  # noise scale η
ITO_MODES  = ["full", "cb_only", "ode_only"]

# Fixed CB: cb_original (the one with the 2026 self-lock)
CB_HALT    = 0.08
CB_RESUME  = 0.01
CB_WINDOW  = 180   # days

# ── Fisher noise helpers ─────────────────────────────────────────────────────

def fisher_weight_noise_sqrt(Sigma_cap: np.ndarray, eps: float = 1e-10) -> tuple[np.ndarray, int]:
    """Compute I_X^{-1/2} in weight space (Fisher-optimal noise matrix, G2.2).

    I_X = A^T G A   where G = Sigma_cap^{-1}   (information metric in weight space)
    Σ_noise = sqrt(η · DT) · I_X^{-1/2}       (per-step noise covariance)

    Returns
    -------
    Sigma_w_sqrt : (N_STATE, N_STATE) — noise covariance matrix (before η, DT scaling)
    rank_Ix      : int — rank of I_X (= N_STATE for non-degenerate calibration)

    Note: Itô correction per bar = η · DT · rank_Ix   (from G2.1, on target set)
    """
    G         = np.linalg.inv(Sigma_cap)
    I_X       = A_FACTORS.T @ G @ A_FACTORS          # (N_STATE, N_STATE) = 3×3
    vals, vecs = np.linalg.eigh(I_X)
    rank_Ix   = int(np.sum(vals > eps * vals[-1]))    # numerical rank
    inv_sqrt  = np.zeros_like(vals)
    for i in range(rank_Ix):
        inv_sqrt[i] = 1.0 / np.sqrt(max(vals[i], eps))
    Sigma_w_sqrt = vecs @ np.diag(inv_sqrt) @ vecs.T # I_X^{-1/2} pseudo-inverse sqrt
    return Sigma_w_sqrt, rank_Ix


def c_sigma_per_bar(eta: float, rank_Ix: int) -> float:
    """Itô energy correction per bar: c_σ = η · DT · rank(I_X)  (from G2.1).

    This is the bounded-above per-bar contribution to E[E] from the noise term.
    Accumulated over N bars: c_σ_total = c_σ_per_bar × N.
    """
    return eta * DT * rank_Ix


# ── Stochastic canonical ODE sweep ──────────────────────────────────────────

def run_godmode_ito(df: pd.DataFrame,
                    train_mask: np.ndarray,
                    test_mask: np.ndarray,
                    w_star_arr: np.ndarray,
                    b_arr: np.ndarray,
                    Sigma_cap: np.ndarray,
                    theta_base: float,
                    eta: float,
                    Sigma_w_sqrt: np.ndarray,
                    kappa: float = KAPPA_A,
                    seed: int = 42,
                    label: str = "") -> pd.DataFrame:
    """Itô-canonical ODE sweep: deterministic drift + Fisher-optimal noise.

    Implements G2.1 canonical SDE:
      dw = H(w)dt + sqrt(η · DT) · Σ_w_sqrt · dW_t

    where H(w) is the existing canonical-ODE drift (identical to v35 run_godmode_sweep)
    and Σ_w_sqrt = I_X^{-1/2} is the Fisher noise matrix (G2.2).

    When η=0 the function is identical to run_godmode_sweep (v35 baseline).
    """
    T    = len(df)
    rng  = np.random.default_rng(seed)
    noise_scale = float(np.sqrt(eta * DT)) if eta > 0 else 0.0

    R = np.column_stack([
        df["ret_btc"].fillna(0.0).values,
        df["ret_eth"].fillna(0.0).values,
        (df["ret_sol"].fillna(0.0).values if "ret_sol" in df.columns
         else df["ret_eth"].fillna(0.0).values),
    ])

    # Calibrate ρ_typ for stale detection (subsample for speed)
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

        # Canonical ODE step (G1.1 Euler) — identical to v35
        w_det = w + DT * sc["rhs"] * conviction

        # Itô noise term: sqrt(η · DT) · Σ_w_sqrt · ξ_t  (G2.1 SDE)
        if noise_scale > 0.0:
            xi    = rng.standard_normal(N_STATE)
            w_sto = noise_scale * (Sigma_w_sqrt @ xi)
        else:
            w_sto = 0.0

        w_new = np.clip(w_det + w_sto, -W_BOX, W_BOX)

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
        log["w_btc"][t]      = w_new[0]
        log["w_eth"][t]      = w_new[1]
        log["w_sol"][t]      = w_new[2]
        log["pnl"][t]        = float(w_new @ R[t])
        log["pnl_long_only"][t] = float(R[t].mean())
        log["stop_flag"][t]  = stop_flag
        log["stale_flag"][t] = stale_flag
        log["drift_flag"][t] = drift_flag
        log["conviction"][t] = conviction
        log["theta_t"][t]    = theta_t

        w           = w_new
        cos_th_prev = sc["cos_theta"]

        if t > 0 and (t % 5000) == 0:
            elapsed = time.time() - t0
            print(f"    [{label}] {t:>6}/{T}  ({elapsed:>5.1f}s)")

    return pd.DataFrame(log, index=df.index)


# ── Stochastic CB simulation ─────────────────────────────────────────────────

def simulate_combined_ito(
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
    ito_c_sigma_bar: float,   # c_σ per bar from G2.4 (= η · DT · rank_Ix)
    use_cb_override: bool,    # G2.4 noise-budget CB unlock
    use_cb:          bool = True,
) -> dict:
    """Extended simulate_combined with Fisher-adaptive CB override (G2.4).

    The deterministic CB logic is identical to v35.

    Fisher-adaptive CB override (G2.4 stochastic ultimate boundedness):
      When the engine is halted, the accumulated Itô budget grows as:
        noise_budget(lock_bars) = ito_c_sigma_bar × lock_bars
      The effective resume condition becomes:
        cb_dd ≤ cb_resume + noise_budget
      Interpretation: the noise budget represents the expected energy range
      compatible with the stochastic steady state — once the residual drawdown
      falls within this range, the regime is no longer distinguishable from the
      Itô noise floor (G2.4, admissibility with M_eff = M + c_σ).

    When use_cb_override=False the function is identical to simulate_combined.
    """
    window_bars  = cb_window_days * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq = INIT; peak_alltime = INIT; halted = False
    halt_start_bar = 0
    eq_vals = []; y_vals = []; cb_flags = []; lock_bars_arr = []
    ito_resets = 0

    for bar_i in range(len(unit_normal)):
        ur_n = float(unit_normal.iloc[bar_i])
        ur_c = float(unit_crash.iloc[bar_i])

        # Sliding-window peak (unchanged from v35)
        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((bar_i, eq))
        roll_peak = mono_dq[0][1]

        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak,    1e-12))

        if use_cb:
            if not halted and cb_dd >= cb_halt:
                halted = True
                halt_start_bar = bar_i
            elif halted:
                lock_bars = bar_i - halt_start_bar

                # Standard resume condition
                if cb_dd <= cb_resume:
                    halted = False
                # G2.4 Fisher-adaptive override: noise budget covers the gap
                elif use_cb_override and ito_c_sigma_bar > 0.0:
                    noise_budget = ito_c_sigma_bar * lock_bars
                    if cb_dd <= cb_resume + noise_budget:
                        halted = False
                        ito_resets += 1
        else:
            halted = False

        # Adaptive Y for normal leg (unchanged)
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
    return dict(
        eq            = eqs,
        final         = float(eqs.iloc[-1]),
        cagr          = float((eqs.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe        = float(np.sqrt(24 * 365.25) * rets.mean() / rets.std()) if rets.std() > 0 else 0.0,
        maxdd         = float(dd_s.min()),
        pct_halted    = float(np.mean(cb_flags)),
        n_trips       = int(sum(cb_flags[i] > cb_flags[i - 1] for i in range(1, len(cb_flags)))),
        avg_y         = float(np.mean(y_vals)),
        ito_resets    = ito_resets,
        max_lock_bars = int(max(lock_bars_arr)) if lock_bars_arr else 0,
    )


# ── Downstream unit builder ──────────────────────────────────────────────────

def build_unit_from_log(log_ann: pd.DataFrame, df: pd.DataFrame,
                        w_star: np.ndarray) -> pd.Series:
    """Build unit signal from Itô ODE log using v28 microstructure variant."""
    ohlc_map  = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch        = get_channel_series()
    v27.RT_COST = RT_BPS / 10_000.0

    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                    signal_kind="wstar", use_quadrant=False)
    inputs_q   = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                    signal_kind="wstar", use_quadrant=True)
    inputs     = attach_q_hot(inputs_noq, inputs_q)
    sig_map    = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}")
                  for asset, _, _, idx in ASSETS}
    return v28.run_variant_v28(REG_VARIANT, inputs, sig_map, log_ann)["unit"]


# ── Metrics helpers ───────────────────────────────────────────────────────────

def yoy(eq: pd.Series) -> dict[str, float]:
    return {r["period"][:4]: r["return_pct"] for r in period_table(eq, "Y")}


def result_row(label, sim, test_ts, d, q, eta, ito_mode,
               c_sigma_bar, rank_Ix, sdiag, bdiag) -> dict:
    eq = sim["eq"][sim["eq"].index >= test_ts]
    m  = equity_metrics(eq, label)
    yy = yoy(eq)
    return dict(
        name=label, d=d, q=q, eta=eta, ito_mode=ito_mode,
        c_sigma_bar=c_sigma_bar, rank_Ix=rank_Ix,
        final=m["final"], profit=m["final"] - INIT,
        cagr=m["cagr"], sharpe=m["sharpe"], maxdd=m["maxdd"], calmar=m["calmar"],
        pct_halted=sim.get("pct_halted", float("nan")),
        n_trips=sim.get("n_trips", 0),
        ito_resets=sim.get("ito_resets", 0),
        max_lock_bars=sim.get("max_lock_bars", 0),
        r2023=yy.get("2023", float("nan")), r2024=yy.get("2024", float("nan")),
        r2025=yy.get("2025", float("nan")), r2026=yy.get("2026", float("nan")),
        sigma=sdiag, budget=bdiag,
    )


# ── Plots ──────────────────────────────────────────────────────────────────────

def plot_eta_vs_r2026(results: list[dict]) -> str:
    """For each (d,q) rank: r2026, Calmar, MaxDD, halt% vs η per ito_mode."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    etas = sorted(set(r["eta"] for r in results))
    modes_color = {"full": "steelblue", "cb_only": "darkorange", "ode_only": "forestgreen"}
    paths = []
    for rank_idx, (d, q) in enumerate(TOP5, 1):
        sub = [r for r in results if r["d"] == d and r["q"] == q]
        if not sub:
            continue
        fig, axes = plt.subplots(2, 2, figsize=(13, 9), sharex=True)
        ax_r26, ax_cal, ax_dd, ax_hlt = axes[0, 0], axes[0, 1], axes[1, 0], axes[1, 1]
        for mode in ITO_MODES:
            rows = sorted([r for r in sub if r["ito_mode"] == mode], key=lambda r: r["eta"])
            if not rows:
                continue
            xs = [r["eta"] for r in rows]
            col = modes_color.get(mode, "gray")
            ax_r26.plot(xs, [r["r2026"] for r in rows], marker="o", color=col, label=mode)
            ax_cal.plot(xs, [r["calmar"] for r in rows], marker="o", color=col, label=mode)
            ax_dd.plot(xs, [r["maxdd"] * 100 for r in rows], marker="o", color=col)
            ax_hlt.plot(xs, [r["pct_halted"] * 100 for r in rows], marker="o", color=col)
        # η=0 baseline (v35)
        base = [r for r in sub if r["eta"] == 0.0]
        if base:
            for ax, fld in [(ax_r26, "r2026"), (ax_cal, "calmar"),
                            (ax_dd, "maxdd"), (ax_hlt, "pct_halted")]:
                val = base[0][fld] * (100 if fld in ("maxdd", "pct_halted") else 1)
                ax.axhline(val, color="red", ls="--", lw=1.2, alpha=0.6,
                           label="v35 baseline" if fld == "r2026" else "")

        ax_r26.set_ylabel("r2026"); ax_r26.legend(fontsize=8)
        ax_cal.set_ylabel("Calmar"); ax_cal.legend(fontsize=8)
        ax_dd.set_ylabel("MaxDD (%)"); ax_dd.set_xlabel("η (noise scale)")
        ax_hlt.set_ylabel("Halt%"); ax_hlt.set_xlabel("η (noise scale)")
        for ax in axes.flat:
            ax.grid(True, alpha=0.25)
        fig.suptitle(f"v36 Rank-{rank_idx}: d={d}, q={q}  — η sweep by Itô mode",
                     fontweight="bold")
        out = PLOT_DIR / f"v36_eta_rank{rank_idx}_d{str(d).replace('.','p')}_q{str(q).replace('.','p')}.png"
        fig.tight_layout(); fig.savefig(out, dpi=160); plt.close(fig)
        paths.append(str(out))
    return paths


def plot_equity_curves_best(sim_store: dict[str, dict],
                             best_rows: list[dict], test_ts: pd.Timestamp) -> str:
    """Equity curves: v35 baseline vs best Itô variant per rank."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(len(TOP5), 1, figsize=(16, 4 * len(TOP5)), sharex=True)
    colors = plt.cm.tab10.colors
    for ax_i, (d, q) in enumerate(TOP5):
        ax = axes[ax_i]
        rank_idx = ax_i + 1
        # v35 baseline (η=0)
        base_key = f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}_eta0_full"
        if base_key in sim_store:
            eq = sim_store[base_key]["eq"]
            eq = eq[eq.index >= test_ts]
            ax.semilogy(eq.index, eq.values, color="tomato", lw=1.4,
                        label=f"η=0 (v35)  ${eq.iloc[-1]:,.0f}")
        # Best Itô variant for this rank
        sub_best = [r for r in best_rows if r["d"] == d and r["q"] == q and r["eta"] > 0]
        if sub_best:
            b = max(sub_best, key=lambda r: r["calmar"])
            bk = b["name"]
            if bk in sim_store:
                eq2 = sim_store[bk]["eq"]
                eq2 = eq2[eq2.index >= test_ts]
                ax.semilogy(eq2.index, eq2.values, color=colors[ax_i % 10], lw=1.6,
                            label=f"η={b['eta']:.1e} {b['ito_mode']}  "
                                  f"${eq2.iloc[-1]:,.0f}  Calmar={b['calmar']:.2f}  "
                                  f"r2026={b['r2026']:+.3f}  resets={b['ito_resets']}")
        ax.set_title(f"Rank-{rank_idx}: d={d}, q={q}")
        ax.set_ylabel("Equity ($)"); ax.legend(fontsize=8); ax.grid(True, alpha=0.25)
    axes[-1].set_xlabel("Date")
    fig.suptitle("v36 Itô-BSDT: v35 baseline vs best stochastic variant per rank",
                 fontweight="bold", y=1.01)
    out = PLOT_DIR / "v36_equity_best_vs_baseline.png"
    fig.tight_layout(); fig.savefig(out, dpi=160, bbox_inches="tight"); plt.close(fig)
    return str(out)


def plot_ito_resets_timeline(sim_store_meta: dict[str, dict],
                              results: list[dict]) -> str:
    """Show how many CB resets were stochastic vs standard per variant."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    sub = [r for r in results if r["d"] == TOP5[0][0] and r["q"] == TOP5[0][1]
           and r["ito_mode"] in ("full", "cb_only") and r["eta"] > 0]
    if not sub:
        return ""
    fig, ax = plt.subplots(figsize=(10, 5))
    labels = [f"η={r['eta']:.1e}\n{r['ito_mode']}" for r in sub]
    resets = [r["ito_resets"] for r in sub]
    r2026  = [r["r2026"] for r in sub]
    x = np.arange(len(sub))
    bars = ax.bar(x, resets, color="steelblue", alpha=0.7, label="Itô CB resets")
    ax2 = ax.twinx()
    ax2.plot(x, r2026, "o-", color="darkorange", lw=2, label="r2026")
    ax2.set_ylabel("r2026"); ax2.axhline(0, color="gray", ls="--", lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8)
    ax.set_xlabel("Variant"); ax.set_ylabel("# Itô CB resets")
    ax.set_title(f"v36 Rank-1 (d={TOP5[0][0]}, q={TOP5[0][1]}): Itô resets and r2026")
    ax.legend(loc="upper left"); ax2.legend(loc="upper right")
    ax.grid(True, alpha=0.25)
    out = PLOT_DIR / "v36_ito_resets_rank1.png"
    fig.tight_layout(); fig.savefig(out, dpi=160); plt.close(fig)
    return str(out)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    t0_total = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    n_variants = len(ETA_GRID) * len(TOP5) * len(ITO_MODES)
    print(BAR)
    print("  CRYPTO GODMODE v36 — Itô-BSDT: Real Stochastic + Fisher-Adaptive CB")
    print("  Canonical SDE:  dw = H(w)dt + sqrt(η·DT)·I_X^{-1/2}·dW_t  (G2.1/G2.2)")
    print("  CB override:    unlock when cb_dd ≤ cb_resume + η·DT·rank(I_X)·lock_bars (G2.4)")
    print(f"  η grid:     {ETA_GRID}")
    print(f"  Itô modes:  {ITO_MODES}")
    print(f"  (d,q) grid: {TOP5}")
    print(f"  CB config:  halt={CB_HALT} resume={CB_RESUME} window={CB_WINDOW}d  (cb_original)")
    print(f"  Total variants: {n_variants}  (η=0 deduplicated across modes = fewer ODE runs)")
    print(BAR)

    # ── [0] Microstructure cache ────────────────────────────────────────────
    print("\n[0] Preloading microstructure cache ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        ms = v27._get_ms(sym)
        print(f"  {sym}: {ms.shape}")

    # ── [1] Shared market inputs ───────────────────────────────────────────
    print("\n[1] Building shared market inputs ...")
    df, _      = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask  = np.asarray(df.index >= TEST_START)
    test_ts    = pd.Timestamp(TEST_START)
    factor_R   = build_factor_returns(df)
    w_star     = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned  = build_b_aligned(w_star)
    v27.RT_COST = RT_BPS / 10_000.0

    # ── [2] FFD Sigma + Fisher noise matrices per d ─────────────────────────
    print("\n[2] Building FFD Sigma and Fisher noise matrices ...")
    sigma_store: dict[float, tuple] = {}
    for d in sorted(set(d for d, q in TOP5)):
        Sigma_cap, Sigma_ffd, sdiag, bdiag = build_sigma(factor_R, train_mask, df, d)
        Sigma_w_sqrt, rank_Ix = fisher_weight_noise_sqrt(Sigma_cap)
        G = np.linalg.inv(Sigma_cap)
        I_X = A_FACTORS.T @ G @ A_FACTORS
        kappa_IX = float(np.linalg.cond(I_X))
        print(f"  d={d:.2f}: cond(Sigma_cap)={sdiag['cond_final']:.2f}  "
              f"rank(I_X)={rank_Ix}  κ(I_X)={kappa_IX:.2f}  "
              f"rho_cap={bdiag['rho_cap']:.4f}")
        # G7 conditioning check
        kappa_S0 = float(np.linalg.cond(Sigma_cap))
        psi_star_ratio = 1.0 / np.sqrt(kappa_S0)
        if kappa_S0 > 100:
            print(f"    WARNING G7: κ(Σ₀)={kappa_S0:.1f} > 100 — Ψ*_eff < 10% of ideal")
        else:
            print(f"    G7 check: κ(Σ₀)={kappa_S0:.2f}  Ψ*/Ψ*_ideal={psi_star_ratio:.3f}")
        sigma_store[d] = (Sigma_cap, Sigma_ffd, sdiag, bdiag, Sigma_w_sqrt, rank_Ix)

    # ── [3] Build ODE logs per (d,q,eta) — deduplicate η=0 ─────────────────
    print("\n[3] Running Itô ODE sweeps ...")
    # ODE log store: key = (d, q, eta_ode)
    # For modes 'cb_only' η_ode=0 (same log as baseline), so share the log.
    ode_keys = [(d, q, eta)
                for d, q in TOP5
                for eta in ETA_GRID]
    # Remove duplicates for 'cb_only' mode (they use eta_ode=0 log)
    ode_unique = sorted(set(ode_keys))
    log_store:   dict[tuple, pd.DataFrame] = {}
    unit_store:  dict[tuple, pd.Series]    = {}
    theta_store: dict[tuple, float]        = {}

    for d, q, eta in ode_unique:
        # eta_ode: for 'ode_only' and 'full' modes
        # For 'cb_only', the ODE log reuses (d, q, 0.0)
        log_key = (d, q, eta)
        if log_key in log_store:
            continue   # already built

        Sigma_cap, _, sdiag, bdiag, Sigma_w_sqrt, rank_Ix = sigma_store[d]
        theta = theta_from(b_aligned, train_mask, Sigma_cap, bdiag["budget"], q)
        theta_store[(d, q)] = theta

        mode_label = f"d{d:.2f}_q{q:.2f}_eta{eta:.0e}"
        print(f"  ODE: {mode_label}  θ={theta:.5f}", end="  ", flush=True)
        t_ode = time.time()

        log_ann = run_godmode_ito(
            df, train_mask, test_mask, w_star, b_aligned,
            Sigma_cap, theta, eta=eta,
            Sigma_w_sqrt=Sigma_w_sqrt, kappa=KAPPA_A,
            seed=42, label=mode_label,
        )
        log_store[log_key] = log_ann

        # Build unit signal from this ODE log (expensive — reuse for same log)
        ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol)
                    for _, symbol, _, _ in ASSETS}
        ch = get_channel_series()
        inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                        signal_kind="wstar", use_quadrant=False)
        inputs_q   = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                        signal_kind="wstar", use_quadrant=True)
        inputs     = attach_q_hot(inputs_noq, inputs_q)
        sig_map    = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}")
                      for asset, _, _, idx in ASSETS}
        unit = v28.run_variant_v28(REG_VARIANT, inputs, sig_map, log_ann)["unit"]
        unit_store[log_key] = unit
        print(f"{time.time()-t_ode:.1f}s  unit={len(unit)}")

    # ── [4] CB simulation sweep ─────────────────────────────────────────────
    print(f"\n[4] Running CB simulation sweep ...")
    results:    list[dict]        = []
    sim_store_eq: dict[str, dict] = {}   # store eq for plotting

    for d, q in TOP5:
        Sigma_cap, _, sdiag, bdiag, Sigma_w_sqrt, rank_Ix = sigma_store[d]
        theta = theta_store[(d, q)]
        for eta in ETA_GRID:
            for ito_mode in ITO_MODES:
                # Determine ODE log and CB override settings per mode
                if ito_mode == "full":
                    eta_ode = eta
                    use_override = eta > 0
                elif ito_mode == "cb_only":
                    eta_ode = 0.0   # deterministic ODE, only CB override
                    use_override = eta > 0
                else:  # ode_only
                    eta_ode = eta
                    use_override = False

                # Skip redundant: for η=0 all modes are identical → only run 'full'
                if eta == 0.0 and ito_mode != "full":
                    continue

                log_key  = (d, q, eta_ode)
                unit     = unit_store[log_key]
                c_sb     = c_sigma_per_bar(eta, rank_Ix)  # always use η for CB budget

                label = (f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}"
                         f"_eta{eta:.0e}_{ito_mode}")
                sim = simulate_combined_ito(
                    unit_normal=unit,
                    unit_crash=pd.Series(0.0, index=unit.index),
                    K_normal=K_NORMAL, K_crash=0.0,
                    dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
                    cb_halt=CB_HALT, cb_resume=CB_RESUME,
                    cb_window_days=CB_WINDOW,
                    ito_c_sigma_bar=c_sb,
                    use_cb_override=use_override,
                )
                sim_store_eq[label] = sim

                row = result_row(
                    label, sim, test_ts, d, q, eta, ito_mode,
                    c_sb, rank_Ix, sdiag, bdiag,
                )
                results.append(row)

                flag_str = f"resets={sim['ito_resets']}" if use_override else "no_override"
                print(f"  {label[:68]:<68}  "
                      f"cal={row['calmar']:>6.2f}  final=${row['final']:>10,.0f}  "
                      f"r2026={row['r2026']:>+.3f}  halt={row['pct_halted']:.1%}  "
                      f"{flag_str}")

    # ── [5] Summary ─────────────────────────────────────────────────────────
    print(f"\n{BAR}")
    print("  v36 RESULTS SUMMARY")
    print(f"  Total variants: {len(results)}")
    if results:
        best_r26 = max(results, key=lambda r: r["r2026"])
        best_cal = max(results, key=lambda r: r["calmar"])
        print(f"\n  Best r2026:  {best_r26['name']}")
        print(f"               calmar={best_r26['calmar']:.2f}  final=${best_r26['final']:,.0f}  "
              f"r2026={best_r26['r2026']:.4f}  resets={best_r26['ito_resets']}")
        print(f"\n  Best Calmar: {best_cal['name']}")
        print(f"               calmar={best_cal['calmar']:.2f}  final=${best_cal['final']:,.0f}  "
              f"r2026={best_cal['r2026']:.4f}  resets={best_cal['ito_resets']}")

        # Print table for rank-1 (d=0.30, q=0.50)
        print(f"\n  Rank-1 (d=0.30, q=0.50) — η sweep:")
        print(f"  {'eta':>10}  {'mode':<10}  {'calmar':>8}  {'final':>10}  "
              f"{'r2026':>8}  {'halt%':>7}  {'resets':>7}  {'c_σ/bar':>12}")
        r1 = sorted([r for r in results if r["d"] == 0.30 and r["q"] == 0.50],
                    key=lambda r: (r["ito_mode"], r["eta"]))
        for r in r1:
            print(f"  {r['eta']:>10.1e}  {r['ito_mode']:<10}  {r['calmar']:>8.2f}  "
                  f"${r['final']:>9,.0f}  {r['r2026']:>+8.4f}  "
                  f"{r['pct_halted']:>6.1%}  {r['ito_resets']:>7}  "
                  f"{r['c_sigma_bar']:>12.2e}")

    # ── [6] Save results ─────────────────────────────────────────────────────
    print("\n[6] Saving results ...")
    safe_results = []
    for r in results:
        row = {k: v for k, v in r.items() if k not in ("sigma", "budget")}
        safe_results.append(row)
    out_json = OUT_DIR_ / "crypto_godmode_v36_ito_bsdt.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({"results": safe_results, "elapsed": time.time() - t0_total,
                   "eta_grid": ETA_GRID, "ito_modes": ITO_MODES,
                   "top5_dq": TOP5, "cb_config": dict(halt=CB_HALT, resume=CB_RESUME,
                                                        window=CB_WINDOW)},
                  f, indent=2, default=str)
    print(f"  → {out_json}")

    # ── [7] Plots ─────────────────────────────────────────────────────────────
    print("\n[7] Generating plots ...")
    paths_eta = plot_eta_vs_r2026(results)
    print(f"  η-sweep plots: {len(paths_eta)}")
    path_eq = plot_equity_curves_best(sim_store_eq, results, test_ts)
    print(f"  Equity curve plot: {path_eq}")
    path_resets = plot_ito_resets_timeline(sim_store_eq, results)
    if path_resets:
        print(f"  Resets plot: {path_resets}")

    elapsed = time.time() - t0_total
    print(f"\n{BAR}")
    print(f"  v36 COMPLETE  |  elapsed={elapsed:.1f}s  ({elapsed/60:.1f} min)")
    print(BAR)


if __name__ == "__main__":
    main()
