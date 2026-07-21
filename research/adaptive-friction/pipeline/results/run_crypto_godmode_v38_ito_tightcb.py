"""
run_crypto_godmode_v38_ito_tightcb.py
======================================

v38 = Itô-BSDT G2.4 gated override applied to cb_v34_tight
      + G7 covariance regularisation (κ(Σ₀) ≤ κ_max)

Motivation
----------
v37 achieved Calmar=25.18 and r2026=+108% but only $288,433 final equity.
This is because it uses cb_original (halt=8%, resume=1%, window=180d) which
locks the engine so conservatively that it misses much of the 2023–2025 bull run.

v34/v35 best config was cb_v34_tight (halt=8%, resume=4%, window=90d):
  → Final ≈ $730,056, Calmar=17, MaxDD=−35%, r2026=+7%

The higher MaxDD (−35% vs −15%) is the main penalty of cb_v34_tight.
Two new mechanisms from the gap-closure addendum address this:

  G2.4 (Stochastic ultimate boundedness)
  ----------------------------------------
  CB override fires when noise budget covers residual CB drawdown:
    cb_dd ≤ cb_resume + c_σ × lock_bars
  With resume=0.04 (vs 0.01 in v37), the standard threshold is already 4×
  wider → G2.4 fires far more easily → fewer wasted locked bars → the engine
  participates in more of the 2023–2025 upside, avoiding the prolonged halts
  that forced equity flat while the peak aged.

  G7 (Admissibility vs κ(Σ₀) — covariance regularisation)
  ----------------------------------------------------------
  From Prop. G7.1: Ψ* = σθ / √(κ(Σ₀) · λ_max(Σ₀)).
  High κ → small Ψ* → tiny safe disturbance budget → any large drawdown event
  exceeds the admissible region → MaxDD blows up.
  Fix: regularise Σ_cap → Σ_cap + λ*I so κ(Σ_cap) ≤ κ_max.
    λ* = (λ_max − κ_max · λ_min) / (κ_max − 1)  when κ > κ_max, else 0.
  Effect on MaxDD: more uniform weight allocation → reduced concentration risk
  → smaller shock from any single-asset crash.
  Effect on Itô correction (G2.4 practical guidance):
    c_Σ = ½ tr(Σ₀⁻¹ · Σ_noise)
  With regularised Σ₀, c_Σ is smaller → noise injection is gentler → fewer
  stochastic excursions that breach the drawdown threshold.

  G7 practical note: κ_max = 10 is the "safe" threshold from Table G7.3.
  κ_max = 5 provides extra margin at the cost of slightly increased bias in
  the weight targets. We grid over two values to measure the trade-off.

Grid
----
  η         ∈ {0, 5e-5, 1e-4, 2e-4, 3e-4, 5e-4}
  lock_min  ∈ {0, 500, 1000, 2000, 3000}          (bars; G2.4 gate)
  κ_max     ∈ {None, 10, 5}                        (G7 regularisation)
  (d,q)     ∈ TOP3 from v36/v37

  η=0:  no override at any lock_min → 1 baseline per (d,q,κ_max)
  CB:   cb_v34_tight (halt=0.08, resume=0.04, window=90d)

  Effective unique variants:
    Per (d,q,κ_max): 5 non-zero η × 5 lock_min + 1 baseline = 26
    Total: 3 (d,q) × 3 κ_max × 26 = 234

Expected outcome
----------------
  Best combination: κ_max=10, lock_min=0–500, η=1e-4 to 3e-4:
    – G7 regularisation reduces MaxDD from −35% closer to −20%
    – G2.4 (resume=0.04 + budget) keeps engine trading during 2023–2025 bull
    – Final equity: $400k–$600k range (between v37's $288k and v34's $730k)
    – Calmar: 18–24 (G7 improves vs v34/v35 raw, may not reach v37's 25)
    – r2026: > 0 (G2.4 still fires for terminal 2026 lock)

Runtime estimate
----------------
  3 ODE runs × ~90s + 234 CB sims × ~3.5s ≈ 1,090s ≈ 18 min
  (κ_max grids re-use the same ODE unit but different Sigma in CB sims)

Theory references
-----------------
  G2.4 : Stochastic ultimate boundedness (noise budget CB override)
  G7.1  : Admissibility vs κ(Σ₀) (regularisation prescription)
  G7.2  : Ψ* degrades as 1/√κ — regularisation restores safe budget
  G7.3  : κ_max=10 is safe, κ_max=5 is extra margin
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
OUT_DIR_  = Path(OUT_DIR) / "v38_ito_tightcb"
PLOT_DIR  = OUT_DIR_ / "plots"

# TOP3 (d,q) from v36/v37 — same as v37
TOP3 = [
    (0.30, 0.50),   # rank-1: baseline Calmar=23.00
    (0.30, 0.65),   # rank-2: best Calmar=23.98
    (0.25, 0.50),   # rank-3: r2026>0 at high η
]

# ── v38 CB config: cb_v34_tight ───────────────────────────────────────────────
CB_HALT   = 0.08   # same as v34/v35/v37
CB_RESUME = 0.04   # v34_tight (was 0.01 in v37 cb_original)
CB_WINDOW = 90     # days (was 180 in v37 cb_original)

# ── v38 grids ─────────────────────────────────────────────────────────────────
ETA_GRID       = [0.0, 5e-5, 1e-4, 2e-4, 3e-4, 5e-4]
LOCK_MIN_GRID  = [0, 500, 1000, 2000, 3000]
KAPPA_MAX_GRID = [None, 10, 5]   # G7 regularisation: None = no regularisation


# ── G7 regularisation (Proposition G7.1) ────────────────────────────────────

def regularise_sigma_g7(Sigma: np.ndarray, kappa_max: float) -> tuple[np.ndarray, float]:
    """Apply G7 covariance regularisation.

    Replaces Sigma by Sigma + λ*I so that κ(Sigma + λ*I) ≤ kappa_max.
    
    From G7.1:  λ* = (λ_max − κ_max · λ_min) / (κ_max − 1)
    
    Returns (regularised_Sigma, lambda_applied).
    If κ(Sigma) ≤ kappa_max already, returns (Sigma, 0.0) unchanged.
    """
    eigvals = np.linalg.eigvalsh(Sigma)
    lam_max = float(eigvals[-1])
    lam_min = float(max(eigvals[0], 1e-12))
    kappa_cur = lam_max / lam_min
    if kappa_cur <= kappa_max:
        return Sigma, 0.0
    lam_reg = (lam_max - kappa_max * lam_min) / (kappa_max - 1.0)
    lam_reg = max(lam_reg, 0.0)
    Sigma_reg = Sigma + lam_reg * np.eye(Sigma.shape[0])
    return Sigma_reg, float(lam_reg)


# ── Fisher noise helpers (identical to v36/v37) ──────────────────────────────

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


# ── Deterministic canonical ODE (η=0, identical to v35/v37) ─────────────────

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


# ── Gated G2.4 CB simulation (same core as v37, CB params from call sites) ───

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

    Standard resume: cb_dd <= cb_resume

    Gated G2.4 override fires when ALL of:
      1. lock_bars >= lock_min
      2. ito_c_sigma_bar > 0
      3. cb_dd <= cb_resume + c_σ × lock_bars

    With cb_v34_tight (resume=0.04):
      - Natural resume threshold is 4x wider than cb_original (0.01)
      - G2.4 fires more easily (lower residual gap to bridge)
      - Short 2022/2024 trips often self-heal before lock_min is reached
    """
    window_bars  = cb_window_days * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq = INIT; peak_alltime = INIT; halted = False
    halt_start_bar = 0

    eq_vals = []; y_vals = []; cb_flags = []; lock_bars_arr = []
    ito_resets = 0
    reset_bar_log: list[int] = []

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
                    halted = False
                    ito_resets += 1
                    reset_bar_log.append(bar_i)
                    halt_start_bar = bar_i   # fresh accumulation after reset

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


# ── Metrics helpers ───────────────────────────────────────────────────────────

def yow(eq: pd.Series) -> dict[str, float]:
    return {r["period"][:4]: r["return_pct"] for r in period_table(eq, "Y")}


def result_row(label, sim, test_ts, d, q, eta, lock_min, kappa_max,
               c_sigma_bar, rank_Ix, lambda_g7, sdiag, bdiag) -> dict:
    eq = sim["eq"][sim["eq"].index >= test_ts]
    m  = equity_metrics(eq, label)
    yy = yow(eq)
    return dict(
        name=label, d=d, q=q, eta=eta, lock_min=lock_min, kappa_max=kappa_max,
        c_sigma_bar=c_sigma_bar, rank_Ix=rank_Ix, lambda_g7=lambda_g7,
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


# ── Plots ──────────────────────────────────────────────────────────────────────

def plot_g7_comparison(results: list[dict]) -> list[str]:
    """For each (d,q,η): bar chart of MaxDD and Calmar across κ_max values."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for d, q in TOP3:
        # Compare η=0 baselines across κ_max
        base_rows = [r for r in results if r["d"] == d and r["q"] == q
                     and r["eta"] == 0.0]
        base_rows.sort(key=lambda r: str(r["kappa_max"]))

        # Compare best G2.4+G7 per κ_max
        sweet_rows = [r for r in results if r["d"] == d and r["q"] == q
                      and r["eta"] > 0 and r.get("r2026", 0) >= 0]

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        kappas = [str(r["kappa_max"]) for r in base_rows]
        maxdds = [abs(r["maxdd"]) * 100 for r in base_rows]
        calmars = [r["calmar"] for r in base_rows]
        finals  = [r["final"] for r in base_rows]

        ax = axes[0]
        bars = ax.bar(kappas, maxdds, color=["tomato", "steelblue", "green"])
        ax.set_title(f"d={d}, q={q}: MaxDD vs G7 κ_max (η=0 baseline)")
        ax.set_xlabel("κ_max (None=no regularisation)")
        ax.set_ylabel("|MaxDD| (%)")
        for bar, v in zip(bars, maxdds):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.2,
                    f"{v:.1f}%", ha="center", fontsize=9)

        ax = axes[1]
        ax.scatter([r["maxdd"] * 100 for r in sweet_rows],
                   [r["calmar"] for r in sweet_rows],
                   c=["tomato" if r["kappa_max"] is None
                      else ("steelblue" if r["kappa_max"] == 10 else "green")
                      for r in sweet_rows],
                   alpha=0.55, s=40)
        ax.axhline(17.49, ls="--", lw=0.8, color="gray", label="v34/v35 baseline Calmar")
        ax.axvline(-35, ls="--", lw=0.8, color="red", label="v34/v35 MaxDD −35%")
        ax.set_xlabel("MaxDD (%)")
        ax.set_ylabel("Calmar")
        ax.set_title("All G2.4 variants: MaxDD vs Calmar")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.25)
        from matplotlib.patches import Patch
        legend_els = [Patch(color="tomato", label="κ_max=None"),
                      Patch(color="steelblue", label="κ_max=10"),
                      Patch(color="green", label="κ_max=5")]
        ax.legend(handles=legend_els + [
            plt.Line2D([0], [0], ls="--", color="gray", label="v34/v35 Calmar"),
            plt.Line2D([0], [0], ls="--", color="red",  label="v34/v35 MaxDD"),
        ], fontsize=8)

        fig.suptitle(f"v38 G7 impact: d={d}, q={q} | cb_v34_tight | G2.4 gated",
                     fontweight="bold")
        out = PLOT_DIR / f"v38_g7_d{str(d).replace('.','p')}_q{str(q).replace('.','p')}.png"
        fig.tight_layout()
        fig.savefig(out, dpi=160)
        plt.close(fig)
        paths.append(str(out))
    return paths


def plot_heatmap_calmar_r2026(results: list[dict]) -> list[str]:
    """2D heatmap over (η, lock_min) for each (d,q,κ_max)."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for rank_idx, (d, q) in enumerate(TOP3, 1):
        for kappa_max in KAPPA_MAX_GRID:
            sub = [r for r in results if r["d"] == d and r["q"] == q
                   and r["kappa_max"] == kappa_max and r["eta"] > 0]
            if not sub:
                continue
            etas  = sorted(set(r["eta"]      for r in sub))
            lmins = sorted(set(r["lock_min"] for r in sub))
            r2026_mat = np.full((len(etas), len(lmins)), float("nan"))
            cal_mat   = np.full((len(etas), len(lmins)), float("nan"))
            dd_mat    = np.full((len(etas), len(lmins)), float("nan"))

            for r in sub:
                i = etas.index(r["eta"])
                j = lmins.index(r["lock_min"])
                r2026_mat[i, j] = r.get("r2026") or 0.0
                cal_mat[i, j]   = r["calmar"]
                dd_mat[i, j]    = abs(r["maxdd"]) * 100

            km_label = f"κ_max={kappa_max}" if kappa_max else "No G7"
            fig, axes = plt.subplots(1, 3, figsize=(18, 5))
            for ax, mat, title, fmt, cmap in [
                (axes[0], r2026_mat, "r2026",     ".2f", "RdYlGn"),
                (axes[1], cal_mat,   "Calmar",    ".1f", "RdYlGn"),
                (axes[2], dd_mat,    "|MaxDD| %", ".1f", "RdYlGn_r"),
            ]:
                im = ax.imshow(mat, aspect="auto", origin="lower", cmap=cmap)
                ax.set_xticks(range(len(lmins)))
                ax.set_xticklabels([str(lm) for lm in lmins], fontsize=8)
                ax.set_yticks(range(len(etas)))
                ax.set_yticklabels([f"{e:.0e}" for e in etas], fontsize=8)
                ax.set_xlabel("lock_min (bars)", fontsize=9)
                ax.set_ylabel("η", fontsize=9)
                ax.set_title(title, fontweight="bold")
                plt.colorbar(im, ax=ax)
                for i in range(len(etas)):
                    for j in range(len(lmins)):
                        v = mat[i, j]
                        if not np.isnan(v):
                            ax.text(j, i, f"{v:{fmt}}", ha="center", va="center",
                                    fontsize=7, color="black")
            fig.suptitle(
                f"v38 Rank-{rank_idx}: d={d}, q={q} | {km_label} | cb_v34_tight",
                fontweight="bold",
            )
            km_str = str(kappa_max) if kappa_max else "none"
            out = PLOT_DIR / (f"v38_heatmap_rank{rank_idx}_d{str(d).replace('.','p')}"
                              f"_q{str(q).replace('.','p')}_km{km_str}.png")
            fig.tight_layout()
            fig.savefig(out, dpi=160)
            plt.close(fig)
            paths.append(str(out))
    return paths


def plot_equity_best(sim_store: dict[str, dict], results: list[dict],
                     test_ts: pd.Timestamp) -> str:
    """Best Calmar variant per rank × κ_max, with v34 baseline."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    colors_km = {None: "tomato", 10: "steelblue", 5: "green"}
    fig, axes = plt.subplots(len(TOP3), 1, figsize=(16, 4 * len(TOP3)), sharex=True)
    if len(TOP3) == 1:
        axes = [axes]

    for ax_i, (d, q) in enumerate(TOP3):
        ax = axes[ax_i]
        for kappa_max in KAPPA_MAX_GRID:
            base_key = (f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}"
                        f"_eta0_lm0_km{kappa_max}")
            if base_key in sim_store:
                eq = sim_store[base_key]["eq"]
                eq = eq[eq.index >= test_ts]
                km_label = f"κ={kappa_max}" if kappa_max else "no-G7"
                rows = [r for r in results if r["name"] == base_key]
                cal_str = f"{rows[0]['calmar']:.2f}" if rows else "?"
                ax.semilogy(eq.index, eq.values, lw=1.2,
                            color=colors_km.get(kappa_max, "gray"), ls="--",
                            alpha=0.6, label=f"η=0 {km_label}  ${eq.iloc[-1]:,.0f}  Cal={cal_str}")

        # Best by Calmar with r2026 > 0 across all κ_max
        sweet = [r for r in results if r["d"] == d and r["q"] == q
                 and r["eta"] > 0 and r.get("r2026", 0) > 0]
        for km, km_clr in colors_km.items():
            sub_km = [r for r in sweet if r["kappa_max"] == km]
            if not sub_km:
                continue
            best = max(sub_km, key=lambda r: r["calmar"])
            bk   = best["name"]
            if bk in sim_store:
                eq2 = sim_store[bk]["eq"]
                eq2 = eq2[eq2.index >= test_ts]
                km_label = f"κ={km}" if km else "no-G7"
                ax.semilogy(eq2.index, eq2.values, lw=1.8, color=km_clr,
                            label=f"best r2026>0 {km_label}  ${eq2.iloc[-1]:,.0f}  "
                                  f"Cal={best['calmar']:.2f}  MaxDD={best['maxdd']:.1%}  "
                                  f"r2026={best.get('r2026', 0):+.3f}")

        ax.axhline(730056, ls=":", lw=1, color="purple", alpha=0.5, label="v34/v35 $730k")
        ax.set_title(f"v38 Rank-{ax_i+1}: d={d}, q={q}")
        ax.set_ylabel("Equity ($)")
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.25)
    axes[-1].set_xlabel("Date")
    fig.suptitle("v38: cb_v34_tight + G2.4 CB override + G7 regularisation",
                 fontweight="bold", y=1.01)
    out = PLOT_DIR / "v38_equity_best.png"
    fig.tight_layout()
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return str(out)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    t0_total = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    n_km = len(KAPPA_MAX_GRID)
    n_eta_nonzero = len(ETA_GRID) - 1  # exclude η=0
    n_per_dq_km = n_eta_nonzero * len(LOCK_MIN_GRID) + 1  # +1 for η=0 baseline
    n_total = len(TOP3) * n_km * n_per_dq_km

    print(BAR)
    print("  CRYPTO GODMODE v38 — G2.4 Gated CB Override + G7 Covariance Regularisation")
    print("  CB: cb_v34_tight (halt=8%, resume=4%, window=90d)")
    print("  G2.4: CB override fires when lock_bars >= lock_min AND cb_dd <= cb_resume + c_σ*lock")
    print("  G7:   κ(Σ₀) capped at κ_max → tighter admissibility bound → lower MaxDD")
    print(f"  η grid:         {ETA_GRID}")
    print(f"  lock_min grid:  {LOCK_MIN_GRID}")
    print(f"  κ_max grid:     {KAPPA_MAX_GRID}")
    print(f"  (d,q) TOP3:     {TOP3}")
    print(f"  CB config:      halt={CB_HALT}  resume={CB_RESUME}  window={CB_WINDOW}d")
    print(f"  ODE runs:       {len(TOP3)} base × {n_km} κ_max")
    print(f"  CB sim variants: {n_total}")
    print(BAR)

    # ── [0] Microstructure cache ─────────────────────────────────────────────
    print("\n[0] Preloading microstructure cache ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        ms = v27._get_ms(sym)
        print(f"  {sym}: {ms.shape}")

    # ── [1] Shared market inputs ─────────────────────────────────────────────
    print("\n[1] Building shared market inputs ...")
    df, _      = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask  = np.asarray(df.index >= TEST_START)
    test_ts    = pd.Timestamp(TEST_START)
    w_star     = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned  = build_b_aligned(w_star)
    factor_R   = build_factor_returns(df)
    v27.RT_COST = RT_BPS / 10_000.0

    # ── [2] FFD Sigma × κ_max grid ───────────────────────────────────────────
    print("\n[2] Building FFD Sigma + G7 regularisation grid ...")
    sigma_store: dict[tuple, tuple] = {}   # key: (d, kappa_max)

    for d in sorted(set(d for d, q in TOP3)):
        Sigma_base, Sigma_ffd, sdiag, bdiag = build_sigma(factor_R, train_mask, df, d)
        kp_S0_base = float(np.linalg.cond(Sigma_base))
        print(f"\n  d={d:.2f}: raw κ(Σ₀)={kp_S0_base:.2f}")

        for kappa_max in KAPPA_MAX_GRID:
            if kappa_max is None:
                Sigma_cap = Sigma_base
                lam_g7 = 0.0
            else:
                Sigma_cap, lam_g7 = regularise_sigma_g7(Sigma_base, float(kappa_max))

            kp_S0 = float(np.linalg.cond(Sigma_cap))
            Sigma_w_sqrt, rank_Ix = fisher_weight_noise_sqrt(Sigma_cap)
            G     = np.linalg.inv(Sigma_cap)
            I_X   = A_FACTORS.T @ G @ A_FACTORS
            kp_IX = float(np.linalg.cond(I_X))

            km_label = f"κ_max={kappa_max}" if kappa_max else "no-G7"
            print(f"    {km_label:15s}:  λ_g7={lam_g7:.3e}  κ(Σ_cap)={kp_S0:.2f}  "
                  f"rank(I_X)={rank_Ix}  κ(I_X)={kp_IX:.2f}")
            if kp_S0 > 10 and kappa_max is not None:
                print(f"      WARNING: G7 cap {kappa_max} not fully reached — check λ* formula")

            sigma_store[(d, kappa_max)] = (Sigma_cap, Sigma_ffd, sdiag, bdiag,
                                           Sigma_w_sqrt, rank_Ix, lam_g7)

    # c_σ per bar diagnostic
    print("\n  c_σ per bar at representative η values:")
    for d in sorted(set(d for d, q in TOP3)):
        for kappa_max in KAPPA_MAX_GRID:
            _, _, _, _, _, rank_Ix, _ = sigma_store[(d, kappa_max)]
            km_label = f"κ_max={kappa_max}" if kappa_max else "no-G7"
            for eta in [1e-4, 3e-4]:
                csb = c_sigma_per_bar(eta, rank_Ix)
                budget_lm0 = csb * 0      # (informational)
                budget_resume = (CB_RESUME + csb * 2000, CB_RESUME + csb * 500)
                print(f"    d={d:.2f} {km_label} η={eta:.0e}:  c_σ/bar={csb:.3e}  "
                      f"budget@500={csb*500:.3f}  budget@2000={csb*2000:.3f}  "
                      f"effective_resume@500={CB_RESUME+csb*500:.3f}  "
                      f"effective_resume@2000={CB_RESUME+csb*2000:.3f}")

    # ── [3] Deterministic ODE sweeps (one per (d,q,κ_max)) ──────────────────
    print("\n[3] Running deterministic ODE sweeps ...")
    unit_store: dict[tuple, pd.Series] = {}   # key: (d, q, kappa_max)

    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol)
                for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()

    for d, q in TOP3:
        for kappa_max in KAPPA_MAX_GRID:
            Sigma_cap, _, sdiag, bdiag, _, rank_Ix, lam_g7 = sigma_store[(d, kappa_max)]
            theta = theta_from(b_aligned, train_mask, Sigma_cap, bdiag["budget"], q)
            km_label = f"km{kappa_max}" if kappa_max else "km_none"
            label = f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}_{km_label}_det"
            print(f"  ODE: {label}  θ={theta:.5f}  λ_g7={lam_g7:.2e}", end="  ", flush=True)
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
            unit_store[(d, q, kappa_max)] = unit
            print(f"{time.time()-t_ode:.1f}s  unit={len(unit)}")

    # ── [4] CB simulation sweep ──────────────────────────────────────────────
    print(f"\n[4] Running CB simulation sweep (G2.4 gated + G7) ...")
    results:      list[dict]      = []
    sim_store_eq: dict[str, dict] = {}

    print(f"\n  {'Variant':<90}  {'Calmar':>7}  {'Final':>12}  {'MaxDD':>7}  "
          f"{'r2026':>7}  {'Halt%':>6}  {'Resets':>6}")
    print(f"  {'-'*90}  {'-'*7}  {'-'*12}  {'-'*7}  {'-'*7}  {'-'*6}  {'-'*6}")

    for d, q in TOP3:
        for kappa_max in KAPPA_MAX_GRID:
            Sigma_cap, _, sdiag, bdiag, _, rank_Ix, lam_g7 = sigma_store[(d, kappa_max)]
            unit = unit_store[(d, q, kappa_max)]
            theta = theta_from(b_aligned, train_mask, Sigma_cap, bdiag["budget"], q)

            for eta in ETA_GRID:
                c_sb = c_sigma_per_bar(eta, rank_Ix)

                for lock_min in LOCK_MIN_GRID:
                    # η=0: no override → only one run per (d,q,kappa_max)
                    if eta == 0.0 and lock_min > 0:
                        continue

                    km_str = str(kappa_max) if kappa_max else "none"
                    label  = (f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}"
                              f"_eta{eta:.0e}_lm{lock_min}_km{km_str}")

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
                        label, sim, test_ts, d, q, eta, lock_min, kappa_max,
                        c_sb, rank_Ix, lam_g7, sdiag, bdiag,
                    )
                    results.append(row)

                    print(f"  {label[:90]:<90}  "
                          f"{row['calmar']:>7.2f}  "
                          f"${row['final']:>11,.0f}  "
                          f"{row['maxdd']:>7.1%}  "
                          f"{row['r2026']:>+7.3f}  "
                          f"{row['pct_halted']:>6.1%}  "
                          f"{sim['ito_resets']:>6}")

    # ── [5] Summary ───────────────────────────────────────────────────────────
    print(f"\n{BAR}")
    print("  v38 RESULTS SUMMARY")
    print(f"  Total variants: {len(results)}")
    print()

    # G7 impact: η=0 baseline MaxDD per κ_max
    print("  G7 impact on baseline MaxDD (η=0):")
    for d, q in TOP3:
        print(f"  (d={d}, q={q}):")
        for kappa_max in KAPPA_MAX_GRID:
            km_str = str(kappa_max) if kappa_max else "none"
            base_key = (f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}"
                        f"_eta0_lm0_km{km_str}")
            rows = [r for r in results if r["name"] == base_key]
            if rows:
                r = rows[0]
                print(f"    κ_max={km_str:5s}:  Calmar={r['calmar']:.2f}  "
                      f"Final=${r['final']:,.0f}  MaxDD={r['maxdd']:.1%}  "
                      f"r2026={r['r2026']:+.3f}")

    # Best r2026 overall
    pos26 = [r for r in results if r.get("r2026", 0) > 0]
    if pos26:
        best_r26 = max(pos26, key=lambda r: r["r2026"])
        print(f"\n  Best r2026:  {best_r26['name']}")
        print(f"    calmar={best_r26['calmar']:.2f}  final=${best_r26['final']:,.0f}  "
              f"r2026={best_r26['r2026']:.4f}  maxdd={best_r26['maxdd']:.1%}  "
              f"κ_max={best_r26['kappa_max']}")
    else:
        print("  Best r2026:  (none > 0)")

    # Best Calmar with r2026 > 0
    sweet = [r for r in results if r.get("r2026", 0) > 0 and r.get("calmar", 0) > 0]
    if sweet:
        best_sw = max(sweet, key=lambda r: r["calmar"])
        print(f"\n  Sweet-spot (best Calmar with r2026>0):  {best_sw['name']}")
        print(f"    calmar={best_sw['calmar']:.2f}  final=${best_sw['final']:,.0f}  "
              f"r2026={best_sw['r2026']:.4f}  maxdd={best_sw['maxdd']:.1%}  "
              f"κ_max={best_sw['kappa_max']}  lock_min={best_sw['lock_min']}  "
              f"resets={best_sw['ito_resets']}")

    # Best Calmar overall
    best_cal = max(results, key=lambda r: r.get("calmar", 0))
    print(f"\n  Best Calmar overall:  {best_cal['name']}")
    print(f"    calmar={best_cal['calmar']:.2f}  final=${best_cal['final']:,.0f}  "
          f"r2026={best_cal['r2026']:.4f}  maxdd={best_cal['maxdd']:.1%}")

    # Best Final with MaxDD > -30% (drawdown improvement over v34)
    dd30 = [r for r in results if r.get("maxdd", -99) > -0.30]
    if dd30:
        best_dd30 = max(dd30, key=lambda r: r.get("final", 0))
        print(f"\n  Best Final with |MaxDD| < 30%:  {best_dd30['name']}")
        print(f"    calmar={best_dd30['calmar']:.2f}  final=${best_dd30['final']:,.0f}  "
              f"r2026={best_dd30['r2026']:.4f}  maxdd={best_dd30['maxdd']:.1%}  "
              f"κ_max={best_dd30['kappa_max']}")

    # v34 comparison
    print(f"\n  v34/v35 reference: $730,056  Calmar=17.49  MaxDD=-35%  r2026=+7%")
    print(f"  v37 reference:     $288,433  Calmar=25.18  MaxDD=-17.4%  r2026=+108%")

    # Sweet-spot scan (d=0.25, q=0.50) across κ_max
    print(f"\n  Sweet-spot scan (d=0.25, q=0.50):")
    for kappa_max in KAPPA_MAX_GRID:
        km_str = str(kappa_max) if kappa_max else "none"
        sub = [r for r in results if r["d"] == 0.25 and r["q"] == 0.50
               and r["kappa_max"] == kappa_max and r["eta"] > 0]
        sub.sort(key=lambda r: (r["lock_min"], r["eta"]))
        print(f"\n  κ_max={km_str}:")
        print(f"  {'lock_min':>8}  {'eta':>9}  {'Calmar':>7}  {'Final':>12}  "
              f"{'MaxDD':>7}  {'r2026':>7}  {'Halt%':>6}  {'Resets':>6}")
        for r in sub[:12]:   # top 12 rows
            print(f"  {r['lock_min']:>8}  {r['eta']:>9.1e}  {r['calmar']:>7.2f}  "
                  f"${r['final']:>11,.0f}  {r['maxdd']:>7.1%}  {r['r2026']:>+7.3f}  "
                  f"{r['pct_halted']:>6.1%}  {r['ito_resets']:>6}")

    # ── [6] Save JSON ──────────────────────────────────────────────────────────
    print(f"\n[6] Saving results ...")
    def serialise(obj):
        if isinstance(obj, float) and (obj != obj or obj == float("inf") or obj == float("-inf")):
            return None
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        raise TypeError(type(obj))

    out_json = OUT_DIR_ / "crypto_godmode_v38_ito_tightcb.json"
    rows_clean = [{k: v for k, v in r.items()
                   if k not in ("sigma", "budget") and not isinstance(v, pd.Series)}
                  for r in results]
    with open(out_json, "w") as f:
        json.dump({"version": "v38", "cb": "cb_v34_tight",
                   "cb_halt": CB_HALT, "cb_resume": CB_RESUME, "cb_window": CB_WINDOW,
                   "results": rows_clean}, f, indent=2, default=serialise)
    print(f"  → {out_json}")

    # ── [7] Plots ──────────────────────────────────────────────────────────────
    print(f"\n[7] Generating plots ...")
    g7_paths = plot_g7_comparison(results)
    print(f"  G7 comparison plots: {len(g7_paths)}")
    hm_paths = plot_heatmap_calmar_r2026(results)
    print(f"  Heatmap plots: {len(hm_paths)}")
    eq_path = plot_equity_best(sim_store_eq, results, test_ts)
    print(f"  Equity curve plot: {eq_path}")

    elapsed = time.time() - t0_total
    print(f"\n{BAR}")
    print(f"  v38 COMPLETE  |  elapsed={elapsed:.1f}s  ({elapsed/60:.1f} min)")
    print(f"  CB: cb_v34_tight (halt={CB_HALT}, resume={CB_RESUME}, window={CB_WINDOW}d)")
    print(f"  Mechanisms: G2.4 gated override + G7 covariance regularisation")
    print(BAR)


if __name__ == "__main__":
    main()
