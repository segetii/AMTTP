# -*- coding: utf-8 -*-
"""
run_crypto_godmode_v47_omega_on_v34_v43_v44.py
================================================

Apply the Mode 1 Omega filter at CB release time to:

  • v34 baseline (simulate_combined, cb_v34_tight: halt=8%, resume=4%, w=90d)
       → currently has NO omega gate
       → produces the $730K result
  • v43 regime CB (simulate_regime_cb_v43)
       → already has omega_thresh=0.02 (we test ON vs OFF)
  • v44 segment trailing stop (simulate_seg_trailstop_v44)
       → already has omega_thresh=0.02 (we test ON vs OFF)

Filter formula (v38_reversal_geometry.py):
    Ω_start = γ_start × ‖f(z_start)‖  <  0.02
    → ALLOW re-entry only if Ω is below threshold
    → measured at the bar where the CB release condition first becomes True

For v34 (no Fix 2, no G2.4 saturating budget): release = first bar where
cb_dd ≤ cb_resume.  This is the MOMENT we evaluate Omega.

Grid:
    (d, q):    TOP3 = [(0.30, 0.50), (0.30, 0.65), (0.25, 0.50)]
    omega:     [None, 0.02]       # off vs on
    algo:      [v34, v43_best, v44_best]
    Total:     3 × 2 × 3 = 18 variants
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
    ANNEAL_AMP, ANNEAL_PEAK, TradingDomain, EPSILON,
)
from run_crypto_canonical_v4 import A_FACTORS, N_STATE, DT, build_factor_returns
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
    build_sigma, theta_from, K_NORMAL, RT_BPS, REG_VARIANT,
)

BAR      = "=" * 110
OUT_DIR_ = Path(OUT_DIR) / "v47_omega_on_v34_v43_v44"
PLOT_DIR = OUT_DIR_ / "plots"

TOP3 = [(0.30, 0.50), (0.30, 0.65), (0.25, 0.50)]

# ── Config slots ──────────────────────────────────────────────────────────────
# v34 cb_v34_tight (the original $730K config)
V34_CB_HALT     = 0.08
V34_CB_RESUME   = 0.04
V34_CB_WINDOW   = 90    # days

# v43 best regime config (from v43 results: REGIME_ma200_bull12_bear8)
V43_CB_HALT_BULL   = 0.12
V43_CB_RESUME_BULL = 0.06
V43_CB_HALT_BEAR   = 0.08
V43_CB_RESUME_BEAR = 0.04
V43_CB_WINDOW      = 90
V43_BTC_MA_BARS    = 200 * 24   # 200d MA

# v44 best trail config (from v44 results: TR047_L14d)
V44_CB_HALT          = 0.08
V44_CB_RESUME        = 0.04
V44_CB_WINDOW        = 90
V44_TRAIL_STOP       = 0.047
V44_TRAIL_LOCKOUT_D  = 14

# Omega gate
OMEGA_THRESH_GRID = [None, 0.02]


# ── Deterministic ODE (same engine used in v45/v46) ───────────────────────────

def run_godmode_det(
    df, train_mask, test_mask, w_star_arr, b_arr,
    Sigma_cap, theta_base, kappa=KAPPA_A, label="",
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
            A=A_FACTORS, b=b_arr[t], Sigma=Sigma_cap, kappa=kappa,
            w_star=w_star_arr[t], theta=theta_base, epsilon=EPSILON,
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
            A=A_FACTORS, b=b_arr[t], Sigma=Sigma_cap, kappa=kappa,
            w_star=w_star_arr[t], theta=theta_t, epsilon=EPSILON,
        ).build()
        sc         = _predictive_scalars(sys_t, w)
        conviction = float(np.clip(-cos_th_prev, CONV_MIN, CONV_MAX))
        w          = np.clip(w + DT * sc["rhs"] * conviction, -W_BOX, W_BOX)

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
        log["stop_flag"][t]     = 1.0 if sc["gamma"] > 0.90 else 0.0
        log["stale_flag"][t]    = 1.0 if (sc["rho_eff"] > 0 and sc["rho_eff"] < 0.1 * rho_typ) else 0.0
        log["drift_flag"][t]    = 1.0 if sc["cos_theta"] > 0.0 else 0.0
        log["conviction"][t]    = conviction
        log["theta_t"][t]       = theta_t
        cos_th_prev = sc["cos_theta"]
        if t > 0 and (t % 5000) == 0:
            print(f"    [{label}] {t:>6}/{T}  ({time.time()-t0:.1f}s)")

    return pd.DataFrame(log, index=df.index), rho_typ


# ── v34 simulator + Omega gate (NEW: minimal omega add to simulate_combined) ──

def simulate_v34_with_omega(
    unit_normal:    pd.Series,
    K_normal:       float,
    cb_halt:        float,
    cb_resume:      float,
    cb_window_days: int,
    gamma_arr:      np.ndarray,
    rhs_norm_arr:   np.ndarray,
    omega_thresh:   float | None,
) -> dict:
    """v34 simulate_combined logic + omega gate at CB release."""
    window_bars = cb_window_days * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq           = INIT
    peak_alltime = INIT
    halted       = False

    eq_vals: list[float] = []
    y_vals:  list[float] = []
    cb_flags:list[int]   = []

    n_omega_blocks = 0
    n_release_evts = 0
    omega_at_release: list[float] = []

    N = len(unit_normal)
    for bar_i in range(N):
        ur_n = float(unit_normal.iloc[bar_i])

        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((bar_i, eq))
        roll_peak = mono_dq[0][1]

        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak,    1e-12))

        # Halt / resume logic with omega gate
        if not halted and cb_dd >= cb_halt:
            halted = True
        elif halted and cb_dd <= cb_resume:
            # Candidate release — apply omega filter
            n_release_evts += 1
            omega_val = float(gamma_arr[bar_i] * rhs_norm_arr[bar_i])
            omega_at_release.append(omega_val)
            if omega_thresh is not None and omega_val >= omega_thresh:
                n_omega_blocks += 1
                # stay halted
            else:
                halted = False

        # Position sizing
        if halted:
            y = 0.0
        elif dd_aty <= DYN_DD_SOFT:
            y = 1.0
        elif dd_aty >= DYN_DD_STOP:
            y = DYN_Y_FLOOR
        else:
            y = DYN_Y_FLOOR + (1.0 - DYN_Y_FLOOR) * (DYN_DD_STOP - dd_aty) / (DYN_DD_STOP - DYN_DD_SOFT)

        r = K_normal * y * ur_n
        r = max(r, -0.95)
        eq          *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)

        eq_vals.append(eq)
        y_vals.append(y)
        cb_flags.append(int(halted))

    eqs   = pd.Series(eq_vals, index=unit_normal.index)
    rets  = eqs.pct_change().fillna(eqs.iloc[0] / INIT - 1.0)
    dd_s  = (eqs - eqs.cummax()) / eqs.cummax()
    years = max((eqs.index[-1] - eqs.index[0]).days / 365.25, 1e-9)

    n_trips = sum(cb_flags[i] > cb_flags[i - 1] for i in range(1, len(cb_flags)))

    return dict(
        eq=eqs,
        final=float(eqs.iloc[-1]),
        cagr=float((eqs.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe=(float(np.sqrt(24 * 365.25) * rets.mean() / rets.std())
                if rets.std() > 0 else 0.0),
        maxdd=float(dd_s.min()),
        pct_halted=float(np.mean(cb_flags)),
        n_trips=n_trips,
        n_omega_blocks=n_omega_blocks,
        n_release_evts=n_release_evts,
        omega_at_release=omega_at_release,
    )


# ── v43 regime CB simulator + omega gate (omega_thresh is a parameter) ────────

def simulate_v43_regime_with_omega(
    unit_normal:    pd.Series,
    K_normal:       float,
    cb_halt_bull:   float, cb_resume_bull: float,
    cb_halt_bear:   float, cb_resume_bear: float,
    cb_window_days: int,
    btc_arr:        np.ndarray,
    btc_ma_arr:     np.ndarray,
    gamma_arr:      np.ndarray,
    rhs_norm_arr:   np.ndarray,
    omega_thresh:   float | None,
) -> dict:
    """Simplified v43 regime CB + omega gate (no Fix2/Fix3 — pure regime CB + Ω)."""
    window_bars = cb_window_days * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq           = INIT
    peak_alltime = INIT
    halted       = False

    eq_vals: list[float] = []
    cb_flags:list[int]   = []
    n_omega_blocks  = 0
    omega_at_release: list[float] = []

    N = len(unit_normal)
    for bar_i in range(N):
        ur_n = float(unit_normal.iloc[bar_i])

        bull = bool(btc_arr[bar_i] > btc_ma_arr[bar_i])
        cb_halt_eff   = cb_halt_bull   if bull else cb_halt_bear
        cb_resume_eff = cb_resume_bull if bull else cb_resume_bear

        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((bar_i, eq))
        roll_peak = mono_dq[0][1]

        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak,    1e-12))

        if not halted and cb_dd >= cb_halt_eff:
            halted = True
        elif halted and cb_dd <= cb_resume_eff:
            omega_val = float(gamma_arr[bar_i] * rhs_norm_arr[bar_i])
            omega_at_release.append(omega_val)
            if omega_thresh is not None and omega_val >= omega_thresh:
                n_omega_blocks += 1
            else:
                halted = False

        if halted:
            y = 0.0
        elif dd_aty <= DYN_DD_SOFT:
            y = 1.0
        elif dd_aty >= DYN_DD_STOP:
            y = DYN_Y_FLOOR
        else:
            y = DYN_Y_FLOOR + (1.0 - DYN_Y_FLOOR) * (DYN_DD_STOP - dd_aty) / (DYN_DD_STOP - DYN_DD_SOFT)

        r = K_normal * y * ur_n
        r = max(r, -0.95)
        eq *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)
        eq_vals.append(eq)
        cb_flags.append(int(halted))

    eqs   = pd.Series(eq_vals, index=unit_normal.index)
    rets  = eqs.pct_change().fillna(eqs.iloc[0] / INIT - 1.0)
    dd_s  = (eqs - eqs.cummax()) / eqs.cummax()
    years = max((eqs.index[-1] - eqs.index[0]).days / 365.25, 1e-9)
    n_trips = sum(cb_flags[i] > cb_flags[i - 1] for i in range(1, len(cb_flags)))

    return dict(
        eq=eqs,
        final=float(eqs.iloc[-1]),
        cagr=float((eqs.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe=(float(np.sqrt(24 * 365.25) * rets.mean() / rets.std())
                if rets.std() > 0 else 0.0),
        maxdd=float(dd_s.min()),
        pct_halted=float(np.mean(cb_flags)),
        n_trips=n_trips,
        n_omega_blocks=n_omega_blocks,
        omega_at_release=omega_at_release,
    )


# ── v44 trail-stop simulator + omega gate ─────────────────────────────────────

def simulate_v44_trail_with_omega(
    unit_normal:        pd.Series,
    K_normal:           float,
    cb_halt:            float, cb_resume: float, cb_window_days: int,
    seg_trail_stop:     float,
    trail_lockout_days: int,
    gamma_arr:          np.ndarray,
    rhs_norm_arr:       np.ndarray,
    omega_thresh:       float | None,
) -> dict:
    """Pure v44 trail-stop logic + omega-at-release gate."""
    window_bars         = cb_window_days * HOURS_PER_DAY
    trail_lockout_bars  = trail_lockout_days * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq            = INIT
    peak_alltime  = INIT
    halt_state    = "active"   # "active" | "cb" | "trail"
    seg_peak_eq   = INIT       # equity peak since last CB release
    trail_release_bar = 0

    eq_vals:  list[float] = []
    cb_flags: list[int]   = []
    n_omega_blocks = 0
    omega_at_release: list[float] = []
    n_trail_halts  = 0

    N = len(unit_normal)
    for bar_i in range(N):
        ur_n = float(unit_normal.iloc[bar_i])

        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((bar_i, eq))
        roll_peak = mono_dq[0][1]

        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak,    1e-12))

        if halt_state == "active":
            seg_peak_eq = max(seg_peak_eq, eq)
            seg_dd      = max(0.0, 1.0 - eq / max(seg_peak_eq, 1e-12))
            if cb_dd >= cb_halt:
                halt_state = "cb"
            elif seg_dd >= seg_trail_stop:
                halt_state = "trail"
                trail_release_bar = bar_i + trail_lockout_bars
                n_trail_halts += 1

        elif halt_state == "cb":
            if cb_dd <= cb_resume:
                omega_val = float(gamma_arr[bar_i] * rhs_norm_arr[bar_i])
                omega_at_release.append(omega_val)
                if omega_thresh is not None and omega_val >= omega_thresh:
                    n_omega_blocks += 1
                else:
                    halt_state  = "active"
                    seg_peak_eq = eq

        elif halt_state == "trail":
            if bar_i >= trail_release_bar:
                halt_state  = "active"
                seg_peak_eq = eq

        # Position sizing
        if halt_state != "active":
            y = 0.0
        elif dd_aty <= DYN_DD_SOFT:
            y = 1.0
        elif dd_aty >= DYN_DD_STOP:
            y = DYN_Y_FLOOR
        else:
            y = DYN_Y_FLOOR + (1.0 - DYN_Y_FLOOR) * (DYN_DD_STOP - dd_aty) / (DYN_DD_STOP - DYN_DD_SOFT)

        r = K_normal * y * ur_n
        r = max(r, -0.95)
        eq *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)
        eq_vals.append(eq)
        cb_flags.append(int(halt_state != "active"))

    eqs   = pd.Series(eq_vals, index=unit_normal.index)
    rets  = eqs.pct_change().fillna(eqs.iloc[0] / INIT - 1.0)
    dd_s  = (eqs - eqs.cummax()) / eqs.cummax()
    years = max((eqs.index[-1] - eqs.index[0]).days / 365.25, 1e-9)
    n_trips = sum(cb_flags[i] > cb_flags[i - 1] for i in range(1, len(cb_flags)))

    return dict(
        eq=eqs,
        final=float(eqs.iloc[-1]),
        cagr=float((eqs.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe=(float(np.sqrt(24 * 365.25) * rets.mean() / rets.std())
                if rets.std() > 0 else 0.0),
        maxdd=float(dd_s.min()),
        pct_halted=float(np.mean(cb_flags)),
        n_trips=n_trips,
        n_omega_blocks=n_omega_blocks,
        n_trail_halts=n_trail_halts,
        omega_at_release=omega_at_release,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def yow(eq: pd.Series) -> dict[str, float]:
    return {r["period"][:4]: r["return_pct"] for r in period_table(eq, "Y")}


def row(label, sim, test_ts, d, q, algo, omega_thresh) -> dict:
    eq = sim["eq"][sim["eq"].index >= test_ts]
    m  = equity_metrics(eq, label)
    yy = yow(eq)
    omegas = sim.get("omega_at_release", [])
    return dict(
        name=label, algo=algo, d=d, q=q, omega_thresh=omega_thresh,
        final=m["final"], maxdd=m["maxdd"], calmar=m["calmar"],
        sharpe=m["sharpe"], cagr=m["cagr"],
        pct_halted=sim.get("pct_halted", float("nan")),
        n_trips=sim.get("n_trips", 0),
        n_omega_blocks=sim.get("n_omega_blocks", 0),
        n_trail_halts=sim.get("n_trail_halts", 0),
        omega_release_min=float(min(omegas)) if omegas else float("nan"),
        omega_release_max=float(max(omegas)) if omegas else float("nan"),
        omega_release_mean=float(np.mean(omegas)) if omegas else float("nan"),
        n_release_omegas=len(omegas),
        r2023=yy.get("2023", float("nan")),
        r2024=yy.get("2024", float("nan")),
        r2025=yy.get("2025", float("nan")),
        r2026=yy.get("2026", float("nan")),
    )


# ── Plot ──────────────────────────────────────────────────────────────────────

def plot_omega_effect(sim_store: dict, results: list[dict],
                      test_ts: pd.Timestamp) -> str:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(3, 1, figsize=(17, 12), sharex=True)

    algo_colors = {"v34": "#1f77b4", "v43": "#d62728", "v44": "#2ca02c"}
    algo_titles = {"v34": "v34 baseline (cb_v34_tight)",
                   "v43": "v43 regime CB (bull12/bear8)",
                   "v44": "v44 trail-stop (TR047_L14d)"}

    for ax_i, algo in enumerate(["v34", "v43", "v44"]):
        ax = axes[ax_i]
        for r in results:
            if r["algo"] != algo:
                continue
            label = r["name"]
            if label not in sim_store:
                continue
            eq = sim_store[label]["eq"]
            eq = eq[eq.index >= test_ts]
            ls = "--" if r["omega_thresh"] is None else "-"
            ot = "OFF" if r["omega_thresh"] is None else f"≥{r['omega_thresh']}"
            ax.semilogy(
                eq.index, eq.values, lw=1.6,
                color=algo_colors[algo], ls=ls, alpha=0.85,
                label=(f"d={r['d']} q={r['q']}  Ω={ot}  "
                       f"${eq.iloc[-1]:,.0f}  MaxDD={r['maxdd']:.1%}  "
                       f"Cal={r['calmar']:.1f}  ΩBlk={r['n_omega_blocks']}/{r['n_release_omegas']}"),
            )

        ax.axhline(730_056, ls=":", color="purple", alpha=0.4, label="v34 $730k")
        ax.axhline(617_095, ls=":", color="green",  alpha=0.4, label="v40/v41 $617k")
        ax.axhline(130_672, ls=":", color="blue",   alpha=0.4, label="v45 $131k (180d)")
        ax.set_title(f"{algo_titles[algo]}  —  Ω-at-release filter ON vs OFF",
                     fontweight="bold")
        ax.set_ylabel("Equity ($)")
        ax.legend(fontsize=7, loc="upper left", ncol=2)
        ax.grid(True, alpha=0.25)

    axes[-1].set_xlabel("Date")
    fig.suptitle("v47: Mode 1 Omega filter (γ × ‖f(z)‖ < 0.02) at CB release",
                 fontweight="bold", y=1.005)
    out = PLOT_DIR / "v47_equity_omega_effect.png"
    fig.tight_layout()
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return str(out)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    t0_total = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    print(BAR)
    print("  v47 — Apply Ω = γ × ‖f(z)‖ < 0.02  filter at CB release time")
    print()
    print(f"  Algorithms tested:")
    print(f"    v34: simulate_combined cb_v34_tight  (h={V34_CB_HALT}, r={V34_CB_RESUME}, w={V34_CB_WINDOW}d)")
    print(f"    v43: regime CB  bull(h={V43_CB_HALT_BULL}/r={V43_CB_RESUME_BULL}) bear(h={V43_CB_HALT_BEAR}/r={V43_CB_RESUME_BEAR})  w={V43_CB_WINDOW}d")
    print(f"    v44: trail-stop tr={V44_TRAIL_STOP} lockout={V44_TRAIL_LOCKOUT_D}d  +  cb_v34_tight base")
    print()
    print(f"  Omega threshold grid: {OMEGA_THRESH_GRID}")
    print(f"  (d,q) TOP3:           {TOP3}")
    print(f"  Total variants:       {3 * len(TOP3) * len(OMEGA_THRESH_GRID)}")
    print(BAR)

    # ── [0] Microstructure cache ──────────────────────────────────────────────
    print("\n[0] Preloading microstructure cache ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        ms = v27._get_ms(sym)
        print(f"  {sym}: {ms.shape}")

    # ── [1] Shared inputs ─────────────────────────────────────────────────────
    print("\n[1] Building shared market inputs ...")
    df, _      = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask  = np.asarray(df.index >= TEST_START)
    test_ts    = pd.Timestamp(TEST_START)
    w_star     = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned  = build_b_aligned(w_star)
    factor_R   = build_factor_returns(df)
    v27.RT_COST = RT_BPS / 10_000.0

    # BTC arrays for v43 regime
    btc_arr    = df["btc"].values.astype(float)
    btc_ma_arr = (pd.Series(btc_arr, index=df.index)
                    .rolling(V43_BTC_MA_BARS, min_periods=24).mean()
                    .bfill().values)

    # ── [2] FFD Sigma for each d ──────────────────────────────────────────────
    print("\n[2] Building FFD Sigma ...")
    sigma_store: dict[float, tuple] = {}
    for d in sorted({d_ for d_, _ in TOP3}):
        Sigma_base, Sigma_ffd, sdiag, bdiag = build_sigma(factor_R, train_mask, df, d)
        Sigma_cap = Sigma_base
        kp_raw = float(np.linalg.cond(Sigma_base))
        print(f"  d={d:.2f}  κ(Σ)={kp_raw:.2f}")
        sigma_store[d] = (Sigma_cap, sdiag, bdiag)

    # ── [3] ODE sweeps per (d,q) ──────────────────────────────────────────────
    print("\n[3] Running deterministic ODE sweeps ...")
    unit_store: dict[tuple, tuple] = {}
    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol)
                for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()

    for d, q in TOP3:
        Sigma_cap, sdiag, bdiag = sigma_store[d]
        theta = theta_from(b_aligned, train_mask, Sigma_cap, bdiag["budget"], q)
        label_ode = f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}_v47"
        print(f"  ODE: {label_ode}  θ={theta:.5f}", end="  ", flush=True)
        t_ode = time.time()
        log_ann, rho_typ = run_godmode_det(
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
        print(f"{time.time()-t_ode:.1f}s")

    # ── [4] Run all variants ──────────────────────────────────────────────────
    print(f"\n[4] Running v47 sweep ...")
    results:    list[dict] = []
    sim_store:  dict[str, dict] = {}

    hdr = (f"  {'algo':<5} {'name':<50}  {'Ω':>5}  {'Final':>11}  {'MaxDD':>7}  "
           f"{'Calmar':>7}  {'Trips':>5}  {'ΩBlk':>4}/{'Rel':<3}  r2026")
    print(hdr)
    print("  " + "-" * (len(hdr)))

    for d, q in TOP3:
        unit, log_ann_dq, _ = unit_store[(d, q)]
        idx = unit.index
        gamma_arr    = log_ann_dq["gamma"].reindex(idx).fillna(0.0).values
        rhs_norm_arr = log_ann_dq["rhs_norm"].reindex(idx).fillna(0.0).values
        btc_aligned  = pd.Series(btc_arr, index=df.index).reindex(idx).ffill().bfill().values
        btc_ma_align = pd.Series(btc_ma_arr, index=df.index).reindex(idx).ffill().bfill().values

        for omega_thresh in OMEGA_THRESH_GRID:
            ot_str = "None" if omega_thresh is None else f"{omega_thresh}"

            # ── v34 ──
            label = f"v34_d{str(d).replace('.','p')}_q{str(q).replace('.','p')}_om{ot_str}"
            sim = simulate_v34_with_omega(
                unit_normal=unit, K_normal=K_NORMAL,
                cb_halt=V34_CB_HALT, cb_resume=V34_CB_RESUME,
                cb_window_days=V34_CB_WINDOW,
                gamma_arr=gamma_arr, rhs_norm_arr=rhs_norm_arr,
                omega_thresh=omega_thresh,
            )
            sim_store[label] = sim
            r = row(label, sim, test_ts, d, q, "v34", omega_thresh)
            results.append(r)
            print(f"  v34   {label[:50]:<50}  {ot_str:>5}  ${r['final']:>10,.0f}  "
                  f"{r['maxdd']:>7.1%}  {r['calmar']:>7.2f}  {r['n_trips']:>5}  "
                  f"{r['n_omega_blocks']:>4}/{r['n_release_omegas']:<3}  {r.get('r2026',0):+.3f}")

            # ── v43 ──
            label = f"v43_d{str(d).replace('.','p')}_q{str(q).replace('.','p')}_om{ot_str}"
            sim = simulate_v43_regime_with_omega(
                unit_normal=unit, K_normal=K_NORMAL,
                cb_halt_bull=V43_CB_HALT_BULL, cb_resume_bull=V43_CB_RESUME_BULL,
                cb_halt_bear=V43_CB_HALT_BEAR, cb_resume_bear=V43_CB_RESUME_BEAR,
                cb_window_days=V43_CB_WINDOW,
                btc_arr=btc_aligned, btc_ma_arr=btc_ma_align,
                gamma_arr=gamma_arr, rhs_norm_arr=rhs_norm_arr,
                omega_thresh=omega_thresh,
            )
            sim_store[label] = sim
            r = row(label, sim, test_ts, d, q, "v43", omega_thresh)
            results.append(r)
            print(f"  v43   {label[:50]:<50}  {ot_str:>5}  ${r['final']:>10,.0f}  "
                  f"{r['maxdd']:>7.1%}  {r['calmar']:>7.2f}  {r['n_trips']:>5}  "
                  f"{r['n_omega_blocks']:>4}/{r['n_release_omegas']:<3}  {r.get('r2026',0):+.3f}")

            # ── v44 ──
            label = f"v44_d{str(d).replace('.','p')}_q{str(q).replace('.','p')}_om{ot_str}"
            sim = simulate_v44_trail_with_omega(
                unit_normal=unit, K_normal=K_NORMAL,
                cb_halt=V44_CB_HALT, cb_resume=V44_CB_RESUME, cb_window_days=V44_CB_WINDOW,
                seg_trail_stop=V44_TRAIL_STOP, trail_lockout_days=V44_TRAIL_LOCKOUT_D,
                gamma_arr=gamma_arr, rhs_norm_arr=rhs_norm_arr,
                omega_thresh=omega_thresh,
            )
            sim_store[label] = sim
            r = row(label, sim, test_ts, d, q, "v44", omega_thresh)
            results.append(r)
            print(f"  v44   {label[:50]:<50}  {ot_str:>5}  ${r['final']:>10,.0f}  "
                  f"{r['maxdd']:>7.1%}  {r['calmar']:>7.2f}  {r['n_trips']:>5}  "
                  f"{r['n_omega_blocks']:>4}/{r['n_release_omegas']:<3}  {r.get('r2026',0):+.3f}")

    # ── [5] Diff: ON vs OFF ───────────────────────────────────────────────────
    print(f"\n{BAR}")
    print("  Effect of Ω filter (ON minus OFF) per (algo, d, q)")
    print(f"  {'algo':<5} {'d':>5} {'q':>5}  {'ΔFinal':>13}  {'ΔMaxDD':>8}  {'ΔCalmar':>8}  {'ΩBlk(ON)':>9}")
    print("  " + "-" * 70)
    for algo in ["v34", "v43", "v44"]:
        for d, q in TOP3:
            off = next((r for r in results if r["algo"]==algo and r["d"]==d
                        and r["q"]==q and r["omega_thresh"] is None), None)
            on  = next((r for r in results if r["algo"]==algo and r["d"]==d
                        and r["q"]==q and r["omega_thresh"] is not None), None)
            if off and on:
                d_fin = on["final"] - off["final"]
                d_dd  = on["maxdd"] - off["maxdd"]
                d_cal = on["calmar"] - off["calmar"]
                print(f"  {algo:<5} {d:>5} {q:>5}  ${d_fin:>12,.0f}  "
                      f"{d_dd*100:>+7.2f}%  {d_cal:>+8.2f}  {on['n_omega_blocks']:>9}")

    # ── [6] Save JSON ─────────────────────────────────────────────────────────
    print(f"\n[6] Saving results ...")

    def serialise(o):
        if isinstance(o, float) and (o != o or abs(o) == float("inf")): return None
        if isinstance(o, np.integer): return int(o)
        if isinstance(o, np.floating): return float(o)
        raise TypeError(type(o))

    out_json = OUT_DIR_ / "crypto_godmode_v47_omega_on_v34_v43_v44.json"
    with open(out_json, "w") as f:
        json.dump({
            "version": "v47",
            "filter":  "Omega = gamma * rhs_norm < 0.02 at CB release time",
            "config": {
                "v34": dict(cb_halt=V34_CB_HALT, cb_resume=V34_CB_RESUME, cb_window_d=V34_CB_WINDOW),
                "v43": dict(bull_halt=V43_CB_HALT_BULL, bull_resume=V43_CB_RESUME_BULL,
                            bear_halt=V43_CB_HALT_BEAR, bear_resume=V43_CB_RESUME_BEAR,
                            cb_window_d=V43_CB_WINDOW, ma_bars=V43_BTC_MA_BARS),
                "v44": dict(cb_halt=V44_CB_HALT, cb_resume=V44_CB_RESUME, cb_window_d=V44_CB_WINDOW,
                            seg_trail_stop=V44_TRAIL_STOP, trail_lockout_d=V44_TRAIL_LOCKOUT_D),
            },
            "omega_thresh_grid": OMEGA_THRESH_GRID,
            "results": results,
        }, f, indent=2, default=serialise)
    print(f"  → {out_json}")

    # ── [7] Plot ──────────────────────────────────────────────────────────────
    print(f"\n[7] Generating plot ...")
    p = plot_omega_effect(sim_store, results, test_ts)
    print(f"  → {p}")

    elapsed = time.time() - t0_total
    print(f"\n{BAR}")
    print(f"  v47 COMPLETE  |  elapsed={elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"  Filter: Ω = γ × ‖f(z)‖ < 0.02 at CB release (v34/v43/v44)")
    print(BAR)


if __name__ == "__main__":
    main()
