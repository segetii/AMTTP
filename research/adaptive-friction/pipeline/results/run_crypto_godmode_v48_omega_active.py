# -*- coding: utf-8 -*-
"""
run_crypto_godmode_v48_omega_active.py
=======================================

v48 = Apply Ω = γ × ‖f(z)‖ < 0.02  CONTINUOUSLY DURING ACTIVE TRADING

──────────────────────────────────────────────────────────────────────────────
Why v46/v47 didn't work
──────────────────────────────────────────────────────────────────────────────

  v46: checked Ω at HALT TIME             → Ω ≈ 0 (all 19 trips)
  v47: checked Ω at CB RELEASE TIME       → only 4 blocks, no effect
  Both miss the Mode 1 reversal window. The reversal pattern from v38
  (peak +5%, revert −5%) happens DURING active trading. By the time the
  equity-based CB fires, the loss is already booked and the ODE has begun
  to reconverge → Ω has decayed.

──────────────────────────────────────────────────────────────────────────────
v48 fix: continuous Ω monitor on every active bar
──────────────────────────────────────────────────────────────────────────────

  On every bar where the strategy is active (not in CB halt):
      omega_t = gamma_t * rhs_norm_t

      If omega_t >= omega_halt_thresh:
          → Mode 1 ODE-overexcitement detected
          → emergency halt (y = 0)
          → lock for omega_lockout_bars
          → OR resume earlier when omega_t falls below omega_resume_thresh

  This runs IN PARALLEL with the standard equity-based CB (v34_tight).
  Either trigger can halt; both must clear to resume.

  The hypothesis: most of the −34.6% MaxDD is built up during a few
  bar-clusters where γ*‖f(z)‖ rises above 0.02 and the ODE is fighting
  large unresolved forces. By cutting position to 0 in those windows, the
  per-bar loss → 0 and the Mode 1 reversal damage is bypassed.

──────────────────────────────────────────────────────────────────────────────
Diagnostic first
──────────────────────────────────────────────────────────────────────────────

  Before sweeping, the script reports the empirical distribution of Ω over
  the test set (active periods only):
    - %bars Ω >= 0.005, 0.01, 0.02, 0.04
    - bar-by-bar correlation of Ω with the per-bar loss
    - max Ω during the worst MaxDD window

──────────────────────────────────────────────────────────────────────────────
Grid
────
  omega_halt_thresh    : [0.005, 0.01, 0.02, 0.04]
  omega_resume_thresh  : 0.005   (fixed: hysteresis)
  omega_lockout_days   : [0, 7, 30]   (0 = pure-reactive, no min-lockout)

  TOP3 (d,q) = [(0.30,0.50), (0.30,0.65), (0.25,0.50)]
  Total: 3 × 4 × 3 = 36
"""
from __future__ import annotations

import json
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))

import run_crypto_godmode_v27_all_microstructure as v27
import run_crypto_godmode_v28_canonical_stability as v28
from run_crypto_pairs_v34_full_combined import (
    OUT_DIR, TEST_START, TRAIN_START, build_1h_df,
)
from run_crypto_godmode_v1 import (
    KAPPA_A, W_TARGET_A1, build_b_aligned, build_w_star,
    _predictive_scalars, CONV_MIN, CONV_MAX, W_BOX,
    ANNEAL_AMP, ANNEAL_PEAK, TradingDomain, EPSILON,
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
    TOP5, REG_VARIANT, FFD_THRESHOLD, FFD_MAX_LAG,
    K_NORMAL, RT_BPS, build_sigma, theta_from,
)

BAR      = "=" * 120
OUT_DIR_ = Path(OUT_DIR) / "v48_omega_active"
PLOT_DIR = OUT_DIR_ / "plots"

TOP3 = [(0.30, 0.50), (0.30, 0.65), (0.25, 0.50)]

# v34 baseline CB
CB_HALT       = 0.08
CB_RESUME     = 0.04
CB_WINDOW_D   = 90

# v48 grid
OMEGA_HALT_GRID    = [0.005, 0.01, 0.02, 0.04]
OMEGA_RESUME       = 0.005
OMEGA_LOCKOUT_D_G  = [0, 7, 30]


# ── Deterministic ODE (full log) ─────────────────────────────────────────────

def run_ode(df, train_mask, w_star_arr, b_arr, Sigma_cap, theta_base,
            kappa=KAPPA_A, label=""):
    T = len(df)
    R = np.column_stack([
        df["ret_btc"].fillna(0.0).values,
        df["ret_eth"].fillna(0.0).values,
        (df["ret_sol"].fillna(0.0).values if "ret_sol" in df.columns
         else df["ret_eth"].fillna(0.0).values),
    ])
    rho_train = []
    for t in np.where(train_mask)[0][::50]:
        sys_t = TradingDomain(A=A_FACTORS, b=b_arr[t], Sigma=Sigma_cap, kappa=kappa,
                              w_star=w_star_arr[t], theta=theta_base, epsilon=EPSILON).build()
        sc = _predictive_scalars(sys_t, np.zeros(N_STATE))
        if sc["rho_eff"] > 0:
            rho_train.append(sc["rho_eff"])
    rho_typ = float(np.median(rho_train)) if rho_train else 1.0

    hours = df.index.hour
    keys = ["E","gamma","dE_dt","cos_theta","mfls","v_E","rho_eff","rhs_norm",
            "w_btc","w_eth","w_sol","pnl","pnl_long_only",
            "stop_flag","stale_flag","drift_flag","conviction","theta_t"]
    log = {k: np.zeros(T) for k in keys}
    w           = np.zeros(N_STATE)
    cos_th_prev = 0.0
    t0 = time.time()
    for t in range(T):
        hr      = int(hours[t])
        theta_t = theta_base * (1.0 + ANNEAL_AMP * np.cos(2*np.pi*(hr-ANNEAL_PEAK)/24.0))
        sys_t = TradingDomain(A=A_FACTORS, b=b_arr[t], Sigma=Sigma_cap, kappa=kappa,
                              w_star=w_star_arr[t], theta=theta_t, epsilon=EPSILON).build()
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
        log["stale_flag"][t]    = 1.0 if (sc["rho_eff"] > 0 and sc["rho_eff"] < 0.1*rho_typ) else 0.0
        log["drift_flag"][t]    = 1.0 if sc["cos_theta"] > 0.0 else 0.0
        log["conviction"][t]    = conviction
        log["theta_t"][t]       = theta_t
        cos_th_prev = sc["cos_theta"]
        if t > 0 and (t % 5000) == 0:
            print(f"    [{label}] {t:>6}/{T}  ({time.time()-t0:.1f}s)")
    return pd.DataFrame(log, index=df.index), rho_typ


# ── v48 simulator: v34 CB + continuous active-bar Ω trip ─────────────────────

def simulate_v48(unit_normal: pd.Series, K_normal: float,
                 cb_halt: float, cb_resume: float, cb_window_days: int,
                 gamma_arr: np.ndarray, rhs_norm_arr: np.ndarray,
                 omega_halt_thresh: float | None,
                 omega_resume_thresh: float,
                 omega_lockout_bars: int) -> dict:
    """v34 CB + continuous Ω trip on active bars.

    halted state can be {None, "cb", "omega"}. Either trip halts; both must clear.
    """
    window_bars = cb_window_days * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq           = INIT
    peak_alltime = INIT

    cb_halted    = False
    om_halted    = False
    om_lock_bar  = -10**9   # bar at which omega lockout was set

    eq_vals: list[float] = []
    y_vals:  list[float] = []
    cb_flags:list[int]   = []
    om_flags:list[int]   = []
    om_trips        = 0
    n_release_evts  = 0

    N = len(unit_normal)
    for bar_i in range(N):
        ur_n = float(unit_normal.iloc[bar_i])
        omega_t = float(gamma_arr[bar_i] * rhs_norm_arr[bar_i])

        # ── Sliding-window peak ──
        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((bar_i, eq))
        roll_peak = mono_dq[0][1]

        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak,    1e-12))

        # ── Standard CB trip ──
        if not cb_halted and cb_dd >= cb_halt:
            cb_halted = True
        elif cb_halted and cb_dd <= cb_resume:
            cb_halted = False
            n_release_evts += 1

        # ── Omega trip (continuous) ──
        if omega_halt_thresh is not None:
            if not om_halted and omega_t >= omega_halt_thresh:
                om_halted   = True
                om_lock_bar = bar_i
                om_trips   += 1
            elif om_halted:
                lock_clear = (bar_i - om_lock_bar) >= omega_lockout_bars
                ode_clear  = omega_t < omega_resume_thresh
                if lock_clear and ode_clear:
                    om_halted = False

        halted = cb_halted or om_halted

        # ── Position sizing ──
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
        cb_flags.append(int(cb_halted))
        om_flags.append(int(om_halted))

    eqs   = pd.Series(eq_vals, index=unit_normal.index)
    rets  = eqs.pct_change().fillna(eqs.iloc[0]/INIT - 1.0)
    dd_s  = (eqs - eqs.cummax()) / eqs.cummax()
    years = max((eqs.index[-1] - eqs.index[0]).days / 365.25, 1e-9)
    n_trips = sum(cb_flags[i] > cb_flags[i-1] for i in range(1, len(cb_flags)))

    return dict(
        eq=eqs,
        final=float(eqs.iloc[-1]),
        cagr=float((eqs.iloc[-1]/INIT)**(1/years) - 1.0),
        sharpe=(float(np.sqrt(24*365.25)*rets.mean()/rets.std()) if rets.std()>0 else 0.0),
        maxdd=float(dd_s.min()),
        pct_cb=float(np.mean(cb_flags)),
        pct_om=float(np.mean(om_flags)),
        pct_halted_any=float(np.mean([cb or om for cb, om in zip(cb_flags, om_flags)])),
        n_trips=n_trips,
        n_omega_trips=om_trips,
        n_release_evts=n_release_evts,
    )


def yow(eq):
    return {r["period"][:4]: r["return_pct"] for r in period_table(eq, "Y")}


def row(label, sim, test_ts, d, q, omega_halt, omega_lockout_d):
    eq = sim["eq"][sim["eq"].index >= test_ts]
    m  = equity_metrics(eq, label)
    yy = yow(eq)
    return dict(
        name=label, d=d, q=q,
        omega_halt=omega_halt, omega_lockout_d=omega_lockout_d,
        final=m["final"], maxdd=m["maxdd"], calmar=m["calmar"],
        sharpe=m["sharpe"], cagr=m["cagr"],
        pct_cb=sim["pct_cb"], pct_om=sim["pct_om"],
        pct_halted_any=sim["pct_halted_any"],
        n_trips=sim["n_trips"], n_omega_trips=sim["n_omega_trips"],
        r2023=yy.get("2023", float("nan")),
        r2024=yy.get("2024", float("nan")),
        r2025=yy.get("2025", float("nan")),
        r2026=yy.get("2026", float("nan")),
    )


def diagnostic_omega(unit, log_ann_dq, test_ts, d, q):
    """Print Ω distribution and per-bar loss correlation on the test set."""
    idx = unit.index
    test_idx = idx[idx >= test_ts]
    gamma    = log_ann_dq["gamma"].reindex(test_idx).fillna(0.0).values
    rhsn     = log_ann_dq["rhs_norm"].reindex(test_idx).fillna(0.0).values
    omega    = gamma * rhsn
    ur       = unit.reindex(test_idx).values
    r_normal = K_NORMAL * ur                 # fully-leveraged unit return
    losses   = -np.minimum(r_normal, 0.0)

    print(f"\n  ── Ω diagnostic on test set  d={d} q={q}  (N={len(omega):,} bars) ──")
    for thr in [0.005, 0.01, 0.02, 0.04, 0.08]:
        pct = 100.0 * np.mean(omega >= thr)
        n   = int((omega >= thr).sum())
        loss_in   = float(losses[omega >= thr].sum())
        loss_out  = float(losses[omega <  thr].sum())
        loss_tot  = max(loss_in + loss_out, 1e-12)
        share     = 100.0 * loss_in / loss_tot
        print(f"    Ω≥{thr:<6}: {pct:>5.2f}% bars ({n:>5})  "
              f"loss_share={share:>5.1f}%  Σ-loss-in={loss_in:.4f}")
    print(f"    max Ω = {omega.max():.5f}   median Ω = {np.median(omega):.6f}")
    if omega.std() > 0 and losses.std() > 0:
        corr = float(np.corrcoef(omega, losses)[0, 1])
        print(f"    corr(Ω, per-bar-loss) = {corr:+.4f}")


def plot_v48(sim_store, results, test_ts):
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    n_rows = len(TOP3)
    fig, axes = plt.subplots(n_rows, 1, figsize=(17, 4*n_rows), sharex=True)
    if n_rows == 1: axes = [axes]

    thresh_colors = {None:"#999", 0.005:"#4393c3", 0.01:"#92c5de",
                     0.02:"#d6604d", 0.04:"#8B0000"}
    lock_ls = {0:"-", 7:"--", 30:":"}

    for ax_i, (d, q) in enumerate(TOP3):
        ax = axes[ax_i]
        for r in results:
            if r["d"] != d or r["q"] != q: continue
            label = r["name"]
            if label not in sim_store: continue
            eq = sim_store[label]["eq"]
            eq = eq[eq.index >= test_ts]
            clr = thresh_colors.get(r["omega_halt"], "#888")
            ls  = lock_ls.get(r["omega_lockout_d"], "-")
            oh  = "OFF" if r["omega_halt"] is None else f"≥{r['omega_halt']}"
            ax.semilogy(eq.index, eq.values, lw=1.7, color=clr, ls=ls,
                        label=(f"Ω-halt={oh} lck={r['omega_lockout_d']}d  "
                               f"${eq.iloc[-1]:,.0f}  MaxDD={r['maxdd']:.1%}  "
                               f"Cal={r['calmar']:.1f}  ΩTrips={r['n_omega_trips']}"))
        ax.axhline(617_095, ls=":", color="green",  alpha=0.4, label="v40/v41 $617k")
        ax.axhline(130_672, ls=":", color="blue",   alpha=0.4, label="v45 $131k (180d)")
        ax.axhline(730_056, ls=":", color="purple", alpha=0.4, label="v34 $730k")
        ax.set_title(f"v48 continuous Ω trip — d={d}, q={q}", fontweight="bold")
        ax.set_ylabel("Equity ($)")
        ax.legend(fontsize=7, loc="upper left", ncol=2)
        ax.grid(True, alpha=0.25)
    axes[-1].set_xlabel("Date")
    fig.suptitle("v48: Continuous Ω = γ × ‖f(z)‖ trip during ACTIVE trading",
                 fontweight="bold", y=1.005)
    out = PLOT_DIR / "v48_equity_omega_active.png"
    fig.tight_layout()
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return str(out)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    t0_total = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    print(BAR)
    print("  v48 — Continuous Ω-trip on every ACTIVE bar (not at release)")
    print(f"  Standard CB:    h={CB_HALT}, r={CB_RESUME}, w={CB_WINDOW_D}d (v34_tight)")
    print(f"  Ω halt grid:    {OMEGA_HALT_GRID}  (None = baseline)")
    print(f"  Ω resume:       {OMEGA_RESUME} (hysteresis)")
    print(f"  Ω lockout d:    {OMEGA_LOCKOUT_D_G}")
    print(f"  TOP3 (d,q):     {TOP3}")
    print(BAR)

    print("\n[0] Microstructure cache ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        ms = v27._get_ms(sym); print(f"  {sym}: {ms.shape}")

    print("\n[1] Shared inputs ...")
    df, _      = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask  = np.asarray(df.index >= TEST_START)
    test_ts    = pd.Timestamp(TEST_START)
    w_star     = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned  = build_b_aligned(w_star)
    factor_R   = build_factor_returns(df)
    v27.RT_COST = RT_BPS / 10_000.0

    print("\n[2] FFD Sigma ...")
    sigma_store = {}
    for d in sorted({d_ for d_, _ in TOP3}):
        Sigma_base, _, sdiag, bdiag = build_sigma(factor_R, train_mask, df, d)
        sigma_store[d] = (Sigma_base, sdiag, bdiag)

    print("\n[3] ODE sweeps ...")
    unit_store = {}
    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()
    for d, q in TOP3:
        Sigma_cap, sdiag, bdiag = sigma_store[d]
        theta = theta_from(b_aligned, train_mask, Sigma_cap, bdiag["budget"], q)
        lab = f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}_v48"
        print(f"  ODE: {lab}  θ={theta:.5f}", end="  ", flush=True)
        t_ode = time.time()
        log_ann, rho_typ = run_ode(df, train_mask, w_star, b_aligned, Sigma_cap,
                                   theta, kappa=KAPPA_A, label=lab)
        print(f"ρ_typ={rho_typ:.4f}", end="  ", flush=True)
        inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                         signal_kind="wstar", use_quadrant=False)
        inputs_q   = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                         signal_kind="wstar", use_quadrant=True)
        inputs     = attach_q_hot(inputs_noq, inputs_q)
        sig_map    = {a: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{a}")
                      for a, _, _, idx in ASSETS}
        unit = v28.run_variant_v28(REG_VARIANT, inputs, sig_map, log_ann)["unit"]
        unit_store[(d, q)] = (unit, log_ann, rho_typ)
        print(f"{time.time()-t_ode:.1f}s")

    # ── Diagnostic FIRST ──
    print(f"\n[4] Ω diagnostic on test set ...")
    for d, q in TOP3:
        unit, log_ann, _ = unit_store[(d, q)]
        diagnostic_omega(unit, log_ann, test_ts, d, q)

    # ── Sweep ──
    print(f"\n[5] Running v48 sweep ...")
    results, sim_store = [], {}
    hdr = (f"  {'name':<55}  {'Ωh':>5}  {'lck':>3}  ${'Final':>10}  "
           f"{'MaxDD':>7}  {'Calmar':>7}  {'%CB':>5}  {'%Ω':>5}  {'ΩTr':>4}  r2026")
    print(hdr); print("  " + "-"*(len(hdr)))

    for d, q in TOP3:
        unit, log_ann_dq, _ = unit_store[(d, q)]
        idx = unit.index
        gamma_arr    = log_ann_dq["gamma"].reindex(idx).fillna(0.0).values
        rhs_norm_arr = log_ann_dq["rhs_norm"].reindex(idx).fillna(0.0).values

        # Baseline (Ω OFF)
        label = f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}_omNone"
        sim = simulate_v48(unit, K_NORMAL, CB_HALT, CB_RESUME, CB_WINDOW_D,
                           gamma_arr, rhs_norm_arr,
                           omega_halt_thresh=None,
                           omega_resume_thresh=OMEGA_RESUME,
                           omega_lockout_bars=0)
        sim_store[label] = sim
        r = row(label, sim, test_ts, d, q, None, 0)
        results.append(r)
        print(f"  {label:<55}  {'OFF':>5}  {0:>3}  ${r['final']:>10,.0f}  "
              f"{r['maxdd']:>7.1%}  {r['calmar']:>7.2f}  "
              f"{r['pct_cb']*100:>4.1f}%  {r['pct_om']*100:>4.1f}%  "
              f"{r['n_omega_trips']:>4}  {r.get('r2026',0):+.3f}")

        for omega_halt in OMEGA_HALT_GRID:
            for lock_d in OMEGA_LOCKOUT_D_G:
                label = (f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}"
                         f"_om{str(omega_halt).replace('.','p')}_lk{lock_d:02d}d")
                sim = simulate_v48(unit, K_NORMAL, CB_HALT, CB_RESUME, CB_WINDOW_D,
                                   gamma_arr, rhs_norm_arr,
                                   omega_halt_thresh=omega_halt,
                                   omega_resume_thresh=OMEGA_RESUME,
                                   omega_lockout_bars=lock_d * HOURS_PER_DAY)
                sim_store[label] = sim
                r = row(label, sim, test_ts, d, q, omega_halt, lock_d)
                results.append(r)
                print(f"  {label:<55}  {omega_halt:>5}  {lock_d:>3}  ${r['final']:>10,.0f}  "
                      f"{r['maxdd']:>7.1%}  {r['calmar']:>7.2f}  "
                      f"{r['pct_cb']*100:>4.1f}%  {r['pct_om']*100:>4.1f}%  "
                      f"{r['n_omega_trips']:>4}  {r.get('r2026',0):+.3f}")

    # ── Summary ──
    print(f"\n{BAR}")
    print("  TOP-15 by Calmar:")
    by_cal = sorted(results, key=lambda r: -r.get("calmar", 0))
    print(f"  {'name':<55}  {'Final':>11}  {'MaxDD':>7}  {'Calmar':>7}  {'Sharpe':>7}  {'ΩTr':>4}")
    for r in by_cal[:15]:
        print(f"  {r['name']:<55}  ${r['final']:>10,.0f}  {r['maxdd']:>7.1%}  "
              f"{r['calmar']:>7.2f}  {r['sharpe']:>7.2f}  {r['n_omega_trips']:>4}")

    print(f"\n  TOP-5 by Final (>= $100K):")
    by_fin = sorted([r for r in results if r["final"] >= 100_000],
                    key=lambda r: -r["final"])
    for r in by_fin[:10]:
        print(f"  {r['name']:<55}  ${r['final']:>10,.0f}  {r['maxdd']:>7.1%}  "
              f"{r['calmar']:>7.2f}  {r['sharpe']:>7.2f}  {r['n_omega_trips']:>4}")

    # ── Save JSON ──
    print(f"\n[6] Saving ...")
    def serialise(o):
        if isinstance(o, float) and (o!=o or abs(o)==float("inf")): return None
        if isinstance(o, np.integer): return int(o)
        if isinstance(o, np.floating): return float(o)
        raise TypeError(type(o))
    out_json = OUT_DIR_ / "crypto_godmode_v48_omega_active.json"
    with open(out_json, "w") as f:
        json.dump({
            "version": "v48",
            "filter":  "Continuous Ω = γ × ‖f(z)‖ trip on every active bar",
            "cb_config": dict(halt=CB_HALT, resume=CB_RESUME, window_d=CB_WINDOW_D),
            "omega_grid": dict(halt=OMEGA_HALT_GRID, resume=OMEGA_RESUME,
                                lockout_d=OMEGA_LOCKOUT_D_G),
            "results": results,
        }, f, indent=2, default=serialise)
    print(f"  → {out_json}")

    print("\n[7] Plot ...")
    p = plot_v48(sim_store, results, test_ts)
    print(f"  → {p}")

    elapsed = time.time() - t0_total
    print(f"\n{BAR}")
    print(f"  v48 COMPLETE  |  elapsed={elapsed:.1f}s  ({elapsed/60:.1f} min)")
    print(BAR)


if __name__ == "__main__":
    main()
