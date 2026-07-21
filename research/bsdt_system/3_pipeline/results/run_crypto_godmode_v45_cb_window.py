# -*- coding: utf-8 -*-
"""
run_crypto_godmode_v45_cb_window.py
=====================================

v45 = v41 + Longer CB Window Sweep (Root-Cause Fix for 14-month Staircase MaxDD)

──────────────────────────────────────────────────────────────────────────────
Root Cause Analysis (confirmed through v41–v44)
──────────────────────────────────────────────────────────────────────────────

  MaxDD = −34.6% is accumulated over a 14-month staircase (Nov 2023 → Dec 2024).
  The strategy fires the CB breaker 19 times in sequence, losing ~8% each trip.

  WHY the CB fires 19 times instead of once:
    - CB window = 90 days → rolling peak is the max equity over last 90 days
    - After 90 days of halted flat equity, the 90d peak resets to the halt level
    - The CB condition (cb_dd >= cb_halt) is then satisfied at 0% drawdown from
      the now-lower 90d peak → strategy resumes
    - Market still declining → immediate loss → CB fires again
    - Repeat 19 times → staircase accumulates to −34.6% MaxDD

  ALL PREVIOUS FIXES FAILED for the same reason:
    v41: post-CB ramp reduces trip size but doesn't reduce n_trips
    v42: shorter windows (14-90d) just make it worse; tight halt reduces returns
    v43: regime-switching too loose in bull → more resumptions into decline
    v44: intra-segment trail stop = more halts during 2025 recovery → kills final equity

──────────────────────────────────────────────────────────────────────────────
v45 Fix: Longer CB Window
──────────────────────────────────────────────────────────────────────────────

  With a LONGER rolling window (180d, 270d, 365d):
    - The pre-staircase peak ($639K, Nov 2023) stays "visible" in the peak
      calculation for longer before being replaced by the lower halt-level equity
    - Strategy stays halted until either: market recovers to cb_resume threshold,
      OR the long window expires (at which point the 365d peak finally drops to
      the flat halt-level equity, allowing resume)

  With cb_window = 365d:
    - Strategy halts Nov 2023 at $590K (first 8% drop from $639K peak)
    - Stays halted for ~12-14 months (until the 365d window expires and the $639K
      peak is no longer in the lookback, OR until the market recovers to $613K)
    - In either case: misses the ENTIRE 14-month staircase decline
    - MaxDD ≈ −8% (just the initial first halt)
    - Final equity at start of 2025 bull run ≈ $590K (vs $420K with 90d window)
    - 2025 bull run multiplied from $590K base → better final equity

  KEY INSIGHT:
    The longer window does NOT hurt the 2025 bull run recovery because:
    - When the 365d peak finally expires → strategy resumes at flat $590K
    - The cb_dd at resume = 0% (since peak has decayed to $590K = current eq)
    - Strategy enters the bull run with full equity intact
    - Calmar should improve dramatically (lower MaxDD + better final equity)

──────────────────────────────────────────────────────────────────────────────
Grid
────
  CB_WINDOW_DAYS_GRID : [90, 180, 270, 365, 540]
    → 90d  = current baseline (v40/v41)
    → 180d = 6 months
    → 270d = 9 months
    → 365d = 1 year  (should cover entire Nov2023–Dec2024 staircase)
    → 540d = 1.5 years (extra long — captures even longer staircase regimes)

  CB_HALT_GRID        : [0.08, 0.10]
    → 0.08 = current standard (cb_v34_tight)
    → 0.10 = slightly wider halt (avoids false fires on temporary dips)
    (cb_resume = cb_halt / 2 for symmetry)

  Fixed engine settings (proven from v40/v41):
    η=2e-4, lock_min=500, kappa_max=None, omega_thresh=0.02, rho_alpha=0.5

  (d,q) TOP3 = same as v38–v44

  Total: 3 (d,q) × 5 (window) × 2 (halt) = 30 variants

Theory references
───────────────────
  Root cause:  v44 analysis + staircase structure (19 CB trips)
  CB math:     mono_dq sliding-window max → expires old peak after window_bars
  v38 baseline: cb_v34_tight = halt=8%, resume=4%, window=90d
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
from run_crypto_godmode_v8_multiasset_shell import (
    ASSETS, build_asset_inputs, fetch_futures_ohlcv_symbol,
)
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
OUT_DIR_ = Path(OUT_DIR) / "v45_cb_window"
PLOT_DIR = OUT_DIR_ / "plots"

# TOP3 (d,q) — same as v38–v44
TOP3 = [
    (0.30, 0.50),   # rank-1: baseline Calmar=23.00
    (0.30, 0.65),   # rank-2: best Calmar=23.98
    (0.25, 0.50),   # rank-3: r2026>0 at high η
]

# ── Fixed engine settings (proven from v40/v41) ───────────────────────────────
ETA          = 2e-4
LOCK_MIN     = 500
KAPPA_MAX    = None
OMEGA_THRESH = 0.02
RHO_ALPHA    = 0.5

# ── v45 CB window sweep ────────────────────────────────────────────────────────
# Hypothesis: longer window keeps the pre-staircase peak fresh,
# preventing re-entry into still-declining market for longer.
CB_WINDOW_DAYS_GRID = [90, 180, 270, 365, 540]
CB_HALT_GRID        = [0.08, 0.10]
# cb_resume = cb_halt / 2 for each


# ── G7 + Fisher helpers (unchanged from v43/v44) ─────────────────────────────

def regularise_sigma_g7(
    Sigma: np.ndarray, kappa_max: float
) -> tuple[np.ndarray, float]:
    eigvals = np.linalg.eigvalsh(Sigma)
    lam_max = float(eigvals[-1])
    lam_min = float(max(eigvals[0], 1e-12))
    if lam_max / lam_min <= kappa_max:
        return Sigma, 0.0
    lam_reg = max((lam_max - kappa_max * lam_min) / (kappa_max - 1.0), 0.0)
    return Sigma + lam_reg * np.eye(Sigma.shape[0]), float(lam_reg)


def fisher_weight_noise_sqrt(
    Sigma_cap: np.ndarray, eps: float = 1e-10
) -> tuple[np.ndarray, int]:
    G        = np.linalg.inv(Sigma_cap)
    I_X      = A_FACTORS.T @ G @ A_FACTORS
    vals, vecs = np.linalg.eigh(I_X)
    rank_Ix  = int(np.sum(vals > eps * vals[-1]))
    inv_sqrt = np.zeros_like(vals)
    for i in range(rank_Ix):
        inv_sqrt[i] = 1.0 / np.sqrt(max(vals[i], eps))
    return vecs @ np.diag(inv_sqrt) @ vecs.T, rank_Ix


def c_sigma_saturating(
    eta: float, rank_Ix: int, rho_typ: float, lock_bars: int
) -> float:
    if eta == 0.0 or rho_typ <= 0.0:
        return 0.0
    E_inf = eta * rank_Ix / rho_typ
    return E_inf * (1.0 - np.exp(-rho_typ * lock_bars * DT))


# ── Deterministic ODE (unchanged from v43/v44) ───────────────────────────────

def run_godmode_det_v39(
    df:          pd.DataFrame,
    train_mask:  np.ndarray,
    test_mask:   np.ndarray,
    w_star_arr:  np.ndarray,
    b_arr:       np.ndarray,
    Sigma_cap:   np.ndarray,
    theta_base:  float,
    kappa:       float = KAPPA_A,
    label:       str   = "",
) -> tuple[pd.DataFrame, float]:
    T = len(df)
    R = np.column_stack([
        df["ret_btc"].fillna(0.0).values,
        df["ret_eth"].fillna(0.0).values,
        (df["ret_sol"].fillna(0.0).values if "ret_sol" in df.columns
         else df["ret_eth"].fillna(0.0).values),
    ])

    rho_train: list[float] = []
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
    keys = [
        "E", "gamma", "dE_dt", "cos_theta", "mfls", "v_E", "rho_eff",
        "rhs_norm", "w_btc", "w_eth", "w_sol", "pnl", "pnl_long_only",
        "stop_flag", "stale_flag", "drift_flag", "conviction", "theta_t",
    ]
    log = {k: np.zeros(T) for k in keys}

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

        log["E"][t]             = sc["E"]
        log["gamma"][t]         = sc["gamma"]
        log["dE_dt"][t]         = sc["dE_dt"]
        log["cos_theta"][t]     = sc["cos_theta"]
        log["mfls"][t]          = sc["mfls"]
        log["v_E"][t]           = sc["v_E"]
        log["rho_eff"][t]       = sc["rho_eff"]
        log["rhs_norm"][t]      = sc["rhs_norm"]
        log["w_btc"][t]         = w[0]
        log["w_eth"][t]         = w[1]
        log["w_sol"][t]         = w[2]
        log["pnl"][t]           = float(w @ R[t])
        log["pnl_long_only"][t] = float(R[t].mean())
        log["stop_flag"][t]     = stop_flag
        log["stale_flag"][t]    = stale_flag
        log["drift_flag"][t]    = drift_flag
        log["conviction"][t]    = conviction
        log["theta_t"][t]       = theta_t

        cos_th_prev = sc["cos_theta"]
        if t > 0 and (t % 5000) == 0:
            print(f"    [{label}] {t:>6}/{T}  ({time.time()-t0:.1f}s)")

    return pd.DataFrame(log, index=df.index), rho_typ


# ── CB simulation with configurable window (v45) ─────────────────────────────

def simulate_cb_window_v45(
    unit_normal:    pd.Series,
    unit_crash:     pd.Series,
    K_normal:       float,
    K_crash:        float,
    dd_soft:        float,
    dd_stop:        float,
    y_floor:        float,
    cb_halt:        float,
    cb_resume:      float,
    cb_window_days: int,
    eta:            float,
    rank_Ix:        int,
    rho_typ:        float,
    lock_min:       int,
    gamma_arr:      np.ndarray,
    rhs_norm_arr:   np.ndarray,
    rho_eff_arr:    np.ndarray,
    omega_thresh:   float | None = 0.02,
    rho_alpha:      float = 0.5,
) -> dict:
    """v45: Standard CB simulation with configurable rolling-window length.

    All logic identical to v41 (fix1 Omega, fix2 saturating budget, fix3 rho_eff).

    The KEY parameter is cb_window_days. Longer window means:
      - Pre-staircase peak stays in the lookback for longer
      - Strategy stays halted during the entire staircase decline
      - Resumes only when market recovers OR the window fully expires
    """
    window_bars    = cb_window_days * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq             = INIT
    peak_alltime   = INIT
    halted         = False
    halt_start_bar = 0
    rho_eff_at_halt = rho_typ

    eq_vals:        list[float] = []
    y_vals:         list[float] = []
    cb_flags:       list[int]   = []
    lock_bars_arr:  list[int]   = []

    ito_resets        = 0
    gate_blocks_omega = 0
    gate_blocks_rho   = 0
    reset_bar_log:    list[int]   = []
    rho_halt_log:     list[float] = []

    N = len(unit_normal)

    for bar_i in range(N):
        ur_n = float(unit_normal.iloc[bar_i])
        ur_c = float(unit_crash.iloc[bar_i])

        # ── Sliding-window peak ───────────────────────────────────────────────
        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((bar_i, eq))
        roll_peak = mono_dq[0][1]

        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak,    1e-12))

        # ── Halt trigger ──────────────────────────────────────────────────────
        if not halted and cb_dd >= cb_halt:
            halted          = True
            halt_start_bar  = bar_i
            rho_eff_at_halt = rho_eff_arr[bar_i]

        # ── Resume evaluation ─────────────────────────────────────────────────
        elif halted:
            lock_bars   = bar_i - halt_start_bar
            is_standard = cb_dd <= cb_resume
            is_g24      = (
                not is_standard
                and eta > 0.0
                and lock_bars >= lock_min
                and cb_dd <= cb_resume + c_sigma_saturating(eta, rank_Ix, rho_typ, lock_bars)
            )
            candidate = is_standard or is_g24

            if candidate and omega_thresh is not None:
                omega_val = gamma_arr[bar_i] * rhs_norm_arr[bar_i]
                if omega_val >= omega_thresh:
                    gate_blocks_omega += 1
                    candidate = False

            if candidate and rho_alpha > 0.0:
                ode_shock = rho_eff_at_halt < rho_alpha * rho_typ
                if ode_shock and rho_eff_arr[bar_i] < rho_alpha * rho_typ:
                    gate_blocks_rho += 1
                    candidate = False

            if candidate:
                halted         = False
                halt_start_bar = bar_i
                if is_g24:
                    ito_resets += 1
                    reset_bar_log.append(bar_i)

        # ── Position sizing ───────────────────────────────────────────────────
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
        eq          *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)

        eq_vals.append(eq)
        y_vals.append(y)
        cb_flags.append(int(halted))
        lock_bars_arr.append(bar_i - halt_start_bar if halted else 0)

    eqs  = pd.Series(eq_vals, index=unit_normal.index)
    rets = eqs.pct_change().fillna(eqs.iloc[0] / INIT - 1.0)
    dd_s = (eqs - eqs.cummax()) / eqs.cummax()
    years = max((eqs.index[-1] - eqs.index[0]).days / 365.25, 1e-9)
    reset_ts = [unit_normal.index[b] for b in reset_bar_log if b < N]

    in_halt = False
    for bi in range(N):
        if cb_flags[bi] and not in_halt:
            in_halt = True
            rho_halt_log.append(float(rho_eff_arr[bi]))
        elif not cb_flags[bi] and in_halt:
            in_halt = False

    n_trips    = len(rho_halt_log)
    pct_halted = float(np.mean(cb_flags))

    return dict(
        eq                  = eqs,
        final               = float(eqs.iloc[-1]),
        cagr                = float((eqs.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe              = (float(np.sqrt(24 * 365.25) * rets.mean() / rets.std())
                               if rets.std() > 0 else 0.0),
        maxdd               = float(dd_s.min()),
        pct_halted          = pct_halted,
        n_trips             = n_trips,
        avg_y               = float(np.mean(y_vals)),
        ito_resets          = ito_resets,
        gate_blocks_omega   = gate_blocks_omega,
        gate_blocks_rho     = gate_blocks_rho,
        rho_eff_at_halt_log = rho_halt_log,
        max_lock_bars       = int(max(lock_bars_arr)) if lock_bars_arr else 0,
        reset_ts            = [str(ts) for ts in reset_ts],
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def yow(eq: pd.Series) -> dict[str, float]:
    return {r["period"][:4]: r["return_pct"] for r in period_table(eq, "Y")}


def result_row_v45(
    label: str, sim: dict, test_ts: pd.Timestamp,
    d: float, q: float,
    cb_halt: float, cb_resume: float, cb_window_days: int,
    rank_Ix: int, lambda_g7: float, rho_typ: float,
    sdiag: dict, bdiag: dict,
) -> dict:
    eq = sim["eq"][sim["eq"].index >= test_ts]
    m  = equity_metrics(eq, label)
    yy = yow(eq)
    return dict(
        name=label, d=d, q=q,
        eta=ETA, lock_min=LOCK_MIN, kappa_max=KAPPA_MAX,
        omega_thresh=OMEGA_THRESH, rho_alpha=RHO_ALPHA,
        cb_halt=cb_halt, cb_resume=cb_resume, cb_window_days=cb_window_days,
        rank_Ix=rank_Ix, lambda_g7=lambda_g7, rho_typ=rho_typ,
        final=m["final"], profit=m["final"] - INIT,
        cagr=m["cagr"], sharpe=m["sharpe"], maxdd=m["maxdd"], calmar=m["calmar"],
        pct_halted=sim.get("pct_halted", float("nan")),
        n_trips=sim.get("n_trips", 0),
        ito_resets=sim.get("ito_resets", 0),
        gate_blocks_omega=sim.get("gate_blocks_omega", 0),
        gate_blocks_rho=sim.get("gate_blocks_rho", 0),
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

def plot_equity_v45(
    sim_store: dict[str, dict],
    results:   list[dict],
    test_ts:   pd.Timestamp,
) -> str:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    n_rows = len(TOP3)
    fig, axes = plt.subplots(n_rows, 1, figsize=(17, 4 * n_rows), sharex=True)
    if n_rows == 1:
        axes = [axes]

    window_colors = {
        90:  "#aaaaaa",
        180: "#4393c3",
        270: "#2166ac",
        365: "#d6604d",
        540: "#8B0000",
    }
    halt_ls = {0.08: "-", 0.10: "--"}

    for ax_i, (d, q) in enumerate(TOP3):
        ax = axes[ax_i]

        for cb_halt in CB_HALT_GRID:
            for cb_window in CB_WINDOW_DAYS_GRID:
                sub = [r for r in results
                       if r["d"] == d and r["q"] == q
                       and abs(r["cb_halt"] - cb_halt) < 1e-9
                       and r["cb_window_days"] == cb_window]
                if not sub:
                    continue
                r = sub[0]
                bk = r["name"]
                if bk not in sim_store:
                    continue
                eq2 = sim_store[bk]["eq"][sim_store[bk]["eq"].index >= test_ts]
                clr = window_colors.get(cb_window, "#888888")
                ls  = halt_ls.get(cb_halt, "-")
                blank = "★" if cb_halt == 0.08 and cb_window == 90 else " "
                ax.semilogy(
                    eq2.index, eq2.values, lw=1.8, color=clr, ls=ls,
                    label=(f"{blank}w={cb_window}d h={cb_halt:.0%}  "
                           f"${eq2.iloc[-1]:,.0f}  "
                           f"MaxDD={r['maxdd']:.1%}  "
                           f"Cal={r['calmar']:.1f}  "
                           f"ntrp={r['n_trips']}"),
                )

        ax.axhline(730_056, ls=":", lw=1.0, color="purple", alpha=0.4, label="v34 $730k")
        ax.axhline(617_095, ls=":", lw=1.0, color="green",  alpha=0.4, label="v40 $617k")
        ax.set_title(f"v45 Window sweep — d={d}, q={q}", fontweight="bold")
        ax.set_ylabel("Equity ($)")
        ax.legend(fontsize=6.5, loc="upper left", ncol=2)
        ax.grid(True, alpha=0.25)

    axes[-1].set_xlabel("Date")
    fig.suptitle(
        "v45: CB window sweep (90d→540d)  —  root-cause fix for 14-month staircase",
        fontweight="bold", y=1.01,
    )
    out = PLOT_DIR / "v45_equity_window_sweep.png"
    fig.tight_layout()
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return str(out)


def plot_window_heatmap(results: list[dict]) -> list[str]:
    """Heatmap: (cb_window, cb_halt) → MaxDD and Final equity for each (d,q)."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []

    windows = sorted(CB_WINDOW_DAYS_GRID)
    halts   = sorted(CB_HALT_GRID)

    for d, q in TOP3:
        dd_mat  = np.full((len(windows), len(halts)), float("nan"))
        fin_mat = np.full((len(windows), len(halts)), float("nan"))
        cal_mat = np.full((len(windows), len(halts)), float("nan"))
        trp_mat = np.full((len(windows), len(halts)), float("nan"))

        for r in results:
            if r["d"] != d or r["q"] != q:
                continue
            wi = windows.index(r["cb_window_days"])
            hi = halts.index(r["cb_halt"])
            dd_mat[wi, hi]  = abs(r["maxdd"]) * 100
            fin_mat[wi, hi] = r["final"] / 1000
            cal_mat[wi, hi] = r["calmar"]
            trp_mat[wi, hi] = r["n_trips"]

        fig, axes = plt.subplots(1, 4, figsize=(22, 5))
        halt_labels   = [f"{h:.0%}" for h in halts]
        window_labels = [f"{w}d" for w in windows]

        for ax, mat, title, fmt, cmap in [
            (axes[0], dd_mat,  "|MaxDD| %",    ".1f", "RdYlGn_r"),
            (axes[1], fin_mat, "Final $k",     ".0f", "RdYlGn"),
            (axes[2], cal_mat, "Calmar",        ".1f", "RdYlGn"),
            (axes[3], trp_mat, "n_trips",       ".0f", "RdYlGn_r"),
        ]:
            im = ax.imshow(mat, aspect="auto", origin="lower", cmap=cmap)
            ax.set_xticks(range(len(halts)))
            ax.set_xticklabels(halt_labels, fontsize=9)
            ax.set_yticks(range(len(windows)))
            ax.set_yticklabels(window_labels, fontsize=9)
            ax.set_xlabel("cb_halt", fontsize=9)
            ax.set_ylabel("cb_window", fontsize=9)
            ax.set_title(title, fontweight="bold")
            plt.colorbar(im, ax=ax)
            for ii in range(len(windows)):
                for jj in range(len(halts)):
                    v = mat[ii, jj]
                    if not np.isnan(v):
                        ax.text(jj, ii, f"{v:{fmt}}", ha="center", va="center",
                                fontsize=8, color="black")

        fig.suptitle(f"v45 Heatmap: d={d}, q={q} — CB window × halt threshold",
                     fontweight="bold")
        fname = f"v45_heatmap_d{str(d).replace('.','p')}_q{str(q).replace('.','p')}.png"
        out   = PLOT_DIR / fname
        fig.tight_layout()
        fig.savefig(out, dpi=160)
        plt.close(fig)
        paths.append(str(out))

    return paths


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    t0_total = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    n_total = len(TOP3) * len(CB_WINDOW_DAYS_GRID) * len(CB_HALT_GRID)

    print(BAR)
    print("  CRYPTO GODMODE v45 — CB Window Sweep (Root-Cause Fix for 14-month Staircase)")
    print()
    print("  Root cause: 90d window 'forgets' pre-staircase peak → 19 re-entries")
    print("  Fix: longer window keeps pre-staircase peak alive → strategy stays halted")
    print()
    print(f"  CB_WINDOW_DAYS grid: {CB_WINDOW_DAYS_GRID}")
    print(f"  CB_HALT grid:        {CB_HALT_GRID}  (cb_resume = cb_halt/2)")
    print(f"  Fixed engine:        eta={ETA:.0e}  lm={LOCK_MIN}  km=None  om={OMEGA_THRESH}  ra={RHO_ALPHA}")
    print(f"  (d,q) TOP3:          {TOP3}")
    print(f"  Total variants:      {n_total}")
    print(BAR)

    # ── [0] Microstructure cache ──────────────────────────────────────────────
    print("\n[0] Preloading microstructure cache ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        ms = v27._get_ms(sym)
        print(f"  {sym}: {ms.shape}")

    # ── [1] Shared market inputs ──────────────────────────────────────────────
    print("\n[1] Building shared market inputs ...")
    df, _      = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask  = np.asarray(df.index >= TEST_START)
    test_ts    = pd.Timestamp(TEST_START)
    w_star     = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned  = build_b_aligned(w_star)
    factor_R   = build_factor_returns(df)
    v27.RT_COST = RT_BPS / 10_000.0

    # ── [2] FFD Sigma ─────────────────────────────────────────────────────────
    print("\n[2] Building FFD Sigma ...")
    sigma_store: dict[float, tuple] = {}

    for d in sorted(set(d_ for d_, _ in TOP3)):
        Sigma_base, Sigma_ffd, sdiag, bdiag = build_sigma(factor_R, train_mask, df, d)
        Sigma_cap, lam_g7 = Sigma_base, 0.0
        Sigma_w_sqrt, rank_Ix = fisher_weight_noise_sqrt(Sigma_cap)
        kp_raw = float(np.linalg.cond(Sigma_base))
        print(f"  d={d:.2f}: κ(Σ)={kp_raw:.2f}  rank(I_X)={rank_Ix}")
        sigma_store[d] = (Sigma_cap, Sigma_ffd, sdiag, bdiag, Sigma_w_sqrt, rank_Ix, lam_g7)

    # ── [3] Deterministic ODE sweeps ──────────────────────────────────────────
    print("\n[3] Running deterministic ODE sweeps ...")
    unit_store: dict[tuple, tuple] = {}

    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol)
                for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()

    for d, q in TOP3:
        Sigma_cap, _, sdiag, bdiag, _, rank_Ix, lam_g7 = sigma_store[d]
        theta     = theta_from(b_aligned, train_mask, Sigma_cap, bdiag["budget"], q)
        label_ode = f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}_det_v45"
        print(f"  ODE: {label_ode}  θ={theta:.5f}", end="  ", flush=True)
        t_ode = time.time()

        log_ann, rho_typ = run_godmode_det_v39(
            df, train_mask, test_mask, w_star, b_aligned,
            Sigma_cap, theta, kappa=KAPPA_A, label=label_ode,
        )
        print(f"ρ_typ={rho_typ:.4f}", end="  ", flush=True)

        inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                        signal_kind="wstar", use_quadrant=False)
        inputs_q   = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                        signal_kind="wstar", use_quadrant=True)
        inputs     = attach_q_hot(inputs_noq, inputs_q)
        sig_map    = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}")
                      for asset, _, _, idx in ASSETS}
        unit = v28.run_variant_v28(REG_VARIANT, inputs, sig_map, log_ann)["unit"]
        unit_store[(d, q)] = (unit, log_ann, rho_typ)
        print(f"{time.time()-t_ode:.1f}s  unit={len(unit)}")

    # ── [4] CB window sweep ────────────────────────────────────────────────────
    print(f"\n[4] Running v45 CB window sweep ...")
    results:      list[dict]      = []
    sim_store_eq: dict[str, dict] = {}

    hdr = (f"  {'label':<72}  {'Calmar':>7}  {'Final':>12}  {'MaxDD':>7}  "
           f"{'r2026':>7}  {'pct_h':>6}  {'ntrp':>5}  {'maxlk':>7}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    for d, q in TOP3:
        Sigma_cap, _, sdiag, bdiag, _, rank_Ix, lam_g7 = sigma_store[d]
        unit, log_ann_dq, rho_typ_dq = unit_store[(d, q)]

        idx          = unit.index
        gamma_arr    = log_ann_dq["gamma"].reindex(idx).fillna(0.0).values
        rhs_norm_arr = log_ann_dq["rhs_norm"].reindex(idx).fillna(0.0).values
        rho_eff_arr  = log_ann_dq["rho_eff"].reindex(idx).fillna(rho_typ_dq).values

        for cb_halt in CB_HALT_GRID:
            cb_resume = round(cb_halt / 2.0, 4)

            for cb_window in CB_WINDOW_DAYS_GRID:
                label = (f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}"
                         f"_h{int(cb_halt*100):02d}_r{int(cb_resume*100):02d}"
                         f"_w{cb_window:03d}d")

                sim = simulate_cb_window_v45(
                    unit_normal=unit,
                    unit_crash=pd.Series(0.0, index=unit.index),
                    K_normal=K_NORMAL, K_crash=0.0,
                    dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
                    cb_halt=cb_halt, cb_resume=cb_resume,
                    cb_window_days=cb_window,
                    eta=ETA, rank_Ix=rank_Ix, rho_typ=rho_typ_dq, lock_min=LOCK_MIN,
                    gamma_arr=gamma_arr, rhs_norm_arr=rhs_norm_arr, rho_eff_arr=rho_eff_arr,
                    omega_thresh=OMEGA_THRESH, rho_alpha=RHO_ALPHA,
                )
                sim_store_eq[label] = sim

                row = result_row_v45(
                    label=label, sim=sim, test_ts=test_ts,
                    d=d, q=q,
                    cb_halt=cb_halt, cb_resume=cb_resume, cb_window_days=cb_window,
                    rank_Ix=rank_Ix, lambda_g7=lam_g7, rho_typ=rho_typ_dq,
                    sdiag=sdiag, bdiag=bdiag,
                )
                results.append(row)

                star = " ★" if cb_halt == 0.08 and cb_window == 90 else "  "
                print(f"  {label:<72}  {row['calmar']:>7.2f}  "
                      f"${row['final']:>11,.0f}  {row['maxdd']:>7.1%}  "
                      f"{row['r2026']:>+7.3f}  {sim.get('pct_halted',0):>6.1%}  "
                      f"{sim.get('n_trips',0):>5}  "
                      f"{sim.get('max_lock_bars',0):>7}{star}")

    # ── [5] Summary ────────────────────────────────────────────────────────────
    print(f"\n{BAR}")
    print("  v45 RESULTS SUMMARY")
    print(f"  Total variants: {len(results)}")
    print()

    # ── Pivot: d=0.25, q=0.50 ──
    print("  Window × halt sweep (d=0.25, q=0.50):")
    print(f"  {'cb_window':>9}  {'cb_halt':>7}  {'Calmar':>7}  {'Final':>12}  "
          f"{'MaxDD':>7}  {'r2026':>7}  {'ntrp':>5}  {'max_lock_bars':>13}")
    sub_25 = [r for r in results if r["d"] == 0.25 and r["q"] == 0.50]
    sub_25.sort(key=lambda r: (r["cb_halt"], r["cb_window_days"]))
    for r in sub_25:
        star = " ★ (baseline)" if r["cb_halt"] == 0.08 and r["cb_window_days"] == 90 else ""
        print(f"  {r['cb_window_days']:>9}d  {r['cb_halt']:>7.0%}  {r['calmar']:>7.2f}  "
              f"${r['final']:>11,.0f}  {r['maxdd']:>7.1%}  "
              f"{r['r2026']:>+7.3f}  {r['n_trips']:>5}  "
              f"{r['max_lock_bars']:>13}{star}")

    # ── Best MaxDD improvement ──
    print("\n  All variants sorted by MaxDD (least negative = best):")
    all_sorted = sorted(results, key=lambda r: -r["maxdd"])
    print(f"  {'name':<65}  {'Calmar':>7}  {'Final':>12}  {'MaxDD':>7}  {'r2026':>7}")
    for r in all_sorted[:15]:
        print(f"  {r['name']:<65}  {r['calmar']:>7.2f}  "
              f"${r['final']:>11,.0f}  {r['maxdd']:>7.1%}  {r['r2026']:>+7.3f}")

    # ── Best Calmar ──
    best_cal = max(results, key=lambda r: r.get("calmar", 0))
    print(f"\n  Best Calmar overall: {best_cal['name']}")
    print(f"    Calmar={best_cal['calmar']:.2f}  Final=${best_cal['final']:,.0f}  "
          f"MaxDD={best_cal['maxdd']:.1%}  r2026={best_cal.get('r2026',0):+.4f}  "
          f"n_trips={best_cal['n_trips']}  max_lock={best_cal['max_lock_bars']}")

    # ── Best MaxDD < 20% ──
    dd20 = [r for r in results if r.get("maxdd", -99) > -0.20]
    if dd20:
        best_dd20 = max(dd20, key=lambda r: r.get("final", 0))
        print(f"\n  Best Final with MaxDD < 20%: {best_dd20['name']}")
        print(f"    Calmar={best_dd20['calmar']:.2f}  Final=${best_dd20['final']:,.0f}  "
              f"MaxDD={best_dd20['maxdd']:.1%}  r2026={best_dd20.get('r2026',0):+.4f}")
    else:
        print("\n  (no variant achieved MaxDD < 20%)")

    # ── Window effect on n_trips ──
    print("\n  Effect of window length on n_trips (d=0.30, q=0.50, cb_halt=8%):")
    for r in [r for r in results if r["d"] == 0.30 and r["q"] == 0.50
              and abs(r["cb_halt"] - 0.08) < 1e-9]:
        print(f"    w={r['cb_window_days']:>4}d:  n_trips={r['n_trips']:>3}  "
              f"MaxDD={r['maxdd']:.1%}  pct_halted={r['pct_halted']:.1%}  "
              f"max_lock={r['max_lock_bars']:>6} bars ({r['max_lock_bars']/24:.0f}d)")

    print(f"\n  Reference lines:")
    print(f"    v34/v35:  $730,056  Calmar=17.49  MaxDD=−35%    r2026=+7%")
    print(f"    v40/v41:  $617K     Calmar=16.60  MaxDD=−34.6%  n_trips=19")
    print(f"    v44 best: $15.2K    Calmar=3.71   MaxDD=−33.4%  [trail_stop killed returns]")

    # ── [6] Save JSON ──────────────────────────────────────────────────────────
    print(f"\n[6] Saving results ...")

    def serialise(obj):
        if isinstance(obj, float) and (obj != obj or abs(obj) == float("inf")):
            return None
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        raise TypeError(type(obj))

    out_json = OUT_DIR_ / "crypto_godmode_v45_cb_window.json"
    rows_clean = [
        {k: v for k, v in r.items()
         if k not in ("sigma", "budget", "rho_eff_at_halt_log")
         and not isinstance(v, pd.Series)}
        for r in results
    ]
    with open(out_json, "w") as f:
        json.dump(
            {
                "version":    "v45",
                "rationale": (
                    "90d CB window = root cause of 14-month staircase MaxDD. "
                    "Longer window keeps pre-staircase peak alive, preventing "
                    "re-entry into declining market for longer."
                ),
                "cb_window_grid":  CB_WINDOW_DAYS_GRID,
                "cb_halt_grid":    CB_HALT_GRID,
                "results": rows_clean,
            },
            f, indent=2, default=serialise,
        )
    print(f"  → {out_json}")

    # ── [7] Plots ──────────────────────────────────────────────────────────────
    print(f"\n[7] Generating plots ...")
    eq_path  = plot_equity_v45(sim_store_eq, results, test_ts)
    print(f"  Equity curves: {eq_path}")
    hm_paths = plot_window_heatmap(results)
    print(f"  Heatmaps: {len(hm_paths)}")

    elapsed = time.time() - t0_total
    print(f"\n{BAR}")
    print(f"  v45 COMPLETE  |  elapsed={elapsed:.1f}s  ({elapsed/60:.1f} min)")
    print(f"  CB window sweep: {CB_WINDOW_DAYS_GRID}d  halt: {CB_HALT_GRID}")
    print(f"  Hypothesis: longer window → fewer trips → lower MaxDD → better final")
    print(BAR)


if __name__ == "__main__":
    main()
