# -*- coding: utf-8 -*-
"""
diag_v41_plan.py
----------------
Correct diagnostic using the ACTUAL simulate_combined_lockmin_v40 function.
Answers:
  1. rho_eff at EACH CB halt bar (correct)
  2. Whether MaxDD is inside or outside a CB trip
  3. How many bars elapsed between the last CB resume and the MaxDD bar
  4. omega values during the MaxDD window
Needed to decide v41 strategy.
"""
import sys, pathlib, time, warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR = pathlib.Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

import run_crypto_godmode_v40_rho_halt as v40
import numpy as np
import pandas as pd

print("=" * 80)
print("  v41 PLAN DIAGNOSTIC  (using actual simulate_combined_lockmin_v40)")
print("=" * 80)

# ── Load market data ──────────────────────────────────────────────────────
print("\n[1] Loading market data ...")
t0 = time.time()
from run_crypto_pairs_v34_full_combined import TEST_START, TRAIN_START, build_1h_df
df, _ = build_1h_df(start="2021-01-01", end="2026-06-01")
train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
test_mask  = np.asarray(df.index >= TEST_START)
test_ts    = pd.Timestamp(TEST_START)
print(f"  done ({time.time()-t0:.1f}s)  TEST_START={TEST_START}")

# ── Build ODE for best config: d=0.25, q=0.50, km=None ───────────────────
d, q, kappa_max = 0.25, 0.50, None
print(f"\n[2] Building Σ + ODE: d={d}, q={q}, km={kappa_max} ...")
w_star    = v40.build_w_star(df, W_TARGET=v40.W_TARGET_A1)
b_aligned = v40.build_b_aligned(w_star)
factor_R  = v40.build_factor_returns(df)
Sigma_base, _, sdiag, bdiag = v40.build_sigma(factor_R, train_mask, df, d)
Sigma_cap = Sigma_base   # km=None → no G7 reg
_, rank_Ix = v40.fisher_weight_noise_sqrt(Sigma_cap)
theta = v40.theta_from(b_aligned, train_mask, Sigma_cap, bdiag["budget"], q)
print(f"  θ={theta:.5f}  rank_Ix={rank_Ix}")

log_ann, rho_typ = v40.run_godmode_det_v39(
    df, train_mask, test_mask, w_star, b_aligned,
    Sigma_cap, theta, kappa=v40.KAPPA_A,
    label="diag_v41_d025_q05_kmNone",
)
print(f"  ρ_typ={rho_typ:.4f}")

# ── Build unit signal ─────────────────────────────────────────────────────
print("\n[3] Rebuilding unit signal ...")
ohlc_map   = {sym: v40.fetch_futures_ohlcv_symbol(sym) for _, sym, _, _ in v40.ASSETS}
ch         = v40.get_channel_series()
inputs_noq = v40.build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                    signal_kind="wstar", use_quadrant=False)
inputs_q   = v40.build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                    signal_kind="wstar", use_quadrant=True)
inputs     = v40.attach_q_hot(inputs_noq, inputs_q)
sig_map    = {a: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{a}")
              for a, _, _, idx in v40.ASSETS}
unit       = v40.v28.run_variant_v28(v40.REG_VARIANT, inputs, sig_map, log_ann)["unit"]

idx          = unit.index
gamma_arr    = np.asarray(log_ann["gamma"  ].reindex(idx, fill_value=0.0))
rhs_norm_arr = np.asarray(log_ann["rhs_norm"].reindex(idx, fill_value=0.0))
rho_eff_arr  = np.asarray(log_ann["rho_eff" ].reindex(idx, fill_value=float(rho_typ)))
omega_arr    = gamma_arr * rhs_norm_arr
print(f"  unit length={len(unit)}")

# ── Run actual v40 CB simulation (no gates, η=0) ──────────────────────────
print("\n[4] Running simulate_combined_lockmin_v40 (no gates) ...")
sim = v40.simulate_combined_lockmin_v40(
    unit_normal    = unit,
    unit_crash     = unit,          # K_crash=0 → irrelevant
    K_normal       = v40.K_NORMAL,
    K_crash        = 0.0,
    dd_soft        = v40.DYN_DD_SOFT,
    dd_stop        = v40.DYN_DD_STOP,
    y_floor        = v40.DYN_Y_FLOOR,
    cb_halt        = v40.CB_HALT,
    cb_resume      = v40.CB_RESUME,
    cb_window_days = v40.CB_WINDOW,
    eta            = 0.0,
    rank_Ix        = rank_Ix,
    rho_typ        = rho_typ,
    lock_min       = 500,
    gamma_arr      = gamma_arr,
    rhs_norm_arr   = rhs_norm_arr,
    rho_eff_arr    = rho_eff_arr,
    omega_thresh   = None,
    rho_alpha      = 0.0,
)

eq_series = sim["eq"]
eq_test   = eq_series[eq_series.index >= test_ts]
test_peak = eq_test.cummax()
dd_test   = (eq_test - test_peak) / test_peak
maxdd     = float(dd_test.min())
maxdd_ts  = dd_test.idxmin()

print(f"  n_trips={sim['n_trips']}  MaxDD={maxdd:.1%}  at {maxdd_ts:%Y-%m-%d %H:%M}")
calmar = sim["cagr"] / abs(sim["maxdd"]) if sim["maxdd"] != 0 else 0.0
print(f"  final=${sim['final']:,.0f}  calmar={calmar:.2f}  pct_halted={sim['pct_halted']:.1%}")

# ── Get rho_eff_at_halt_log from the simulation ───────────────────────────
rho_halt_log = sim.get("rho_eff_at_halt_log", [])
print(f"\n  rho_eff_at_halt_log ({len(rho_halt_log)} entries): {[round(v,3) for v in rho_halt_log]}")

# ── Reconstruct halt/resume times from eq series ─────────────────────────
# During CB, equity doesn't change. Find contiguous flat sections.
eq_arr  = eq_series.values
eq_diff = np.diff(eq_arr, prepend=eq_arr[0])
halted_arr = (eq_diff == 0.0).astype(int)
# Refine: look for transitions
halt_starts = np.where(np.diff(halted_arr, prepend=0) == 1)[0]
halt_ends   = np.where(np.diff(halted_arr, prepend=0) == -1)[0]
if len(halt_ends) < len(halt_starts):
    halt_ends = np.append(halt_ends, len(eq_arr) - 1)

print(f"\n  Detected {len(halt_starts)} CB halt periods from flat-equity scan:")
print(f"\n  {'#':>2}  {'Halt bar':>8}  {'Halt date':20}  {'Resume date':20}  "
      f"{'lock_h':>6}  {'ρ_halt':>7}  {'ρ_res':>7}  {'ω_halt':>7}  "
      f"{'eq_halt':>9}  in_test")
print("  " + "─"*115)

for i, (hs, he) in enumerate(zip(halt_starts, halt_ends)):
    ts_h   = str(idx[hs])[:19]   if hs < len(idx)   else "?"
    ts_r   = str(idx[he])[:19]   if he < len(idx)    else "?"
    lock_h = he - hs
    rh     = float(rho_eff_arr[hs])   if hs < len(rho_eff_arr) else float("nan")
    rr     = float(rho_eff_arr[he])   if he < len(rho_eff_arr) else float("nan")
    oh     = float(omega_arr[hs])     if hs < len(omega_arr)   else float("nan")
    eqh    = float(eq_arr[hs])
    intest = "✓" if ts_h >= TEST_START else ""

    flag = ""
    if rh < 0.5 * rho_typ:
        flag = " ← ODE SHOCK (low ρ)"
    elif rh > 3.0 * rho_typ:
        flag = f" ← OVERHEAT (ρ={rh:.1f})"

    print(f"  {i+1:>2}  {hs:>8}  {ts_h:20}  {ts_r:20}  {lock_h:>6}  "
          f"{rh:>7.3f}  {rr:>7.3f}  {oh:>7.4f}  {eqh:>9,.0f}  {intest}{flag}")

# ── MaxDD attribution ─────────────────────────────────────────────────────
maxdd_bar = int(np.searchsorted(idx, maxdd_ts))
print(f"\n  MaxDD analysis:")
print(f"  MaxDD={maxdd:.1%}  bar={maxdd_bar}  ts={maxdd_ts:%Y-%m-%d %H:%M}")
print(f"  Equity at MaxDD: ${eq_arr[maxdd_bar]:,.0f}")

# Is MaxDD bar inside any CB trip?
in_cb = False
for hs, he in zip(halt_starts, halt_ends):
    if hs <= maxdd_bar <= he:
        in_cb = True
        print(f"  MaxDD is INSIDE CB trip {hs}-{he}  "
              f"({str(idx[hs])[:19]} → {str(idx[he])[:19]})")
        break
if not in_cb:
    # find last CB release before MaxDD
    prev_releases = [(hs, he) for hs, he in zip(halt_starts, halt_ends) if he < maxdd_bar]
    if prev_releases:
        last_hs, last_he = prev_releases[-1]
        bars_since_resume = maxdd_bar - last_he
        days_since_resume = bars_since_resume / v40.HOURS_PER_DAY
        print(f"  MaxDD is OUTSIDE CB trips – during NORMAL TRADING")
        print(f"  Last CB resume: {str(idx[last_he])[:19]}  (bar {last_he})")
        print(f"  Bars since last CB resume: {bars_since_resume}  "
              f"= {days_since_resume:.1f} days")
        # omega at MaxDD bar
        om_maxdd = float(omega_arr[maxdd_bar]) if maxdd_bar < len(omega_arr) else float("nan")
        rh_maxdd = float(rho_eff_arr[maxdd_bar]) if maxdd_bar < len(rho_eff_arr) else float("nan")
        print(f"  ρ_eff at MaxDD bar: {rh_maxdd:.4f}  (threshold α=0.5: {0.5*rho_typ:.4f})"
              f"  ω at MaxDD: {om_maxdd:.4f}  (threshold 0.02)")
    else:
        print(f"  MaxDD is OUTSIDE CB trips – no preceding CB in test window")

# ── Omega analysis around MaxDD window (±7 days) ──────────────────────────
window    = 168  # 7 days in bars
om_window = omega_arr[max(0, maxdd_bar-window) : min(len(omega_arr), maxdd_bar+window)]
print(f"\n  Omega in ±7d around MaxDD:  max={om_window.max():.4f}  "
      f"p90={np.percentile(om_window,90):.4f}  p75={np.percentile(om_window,75):.4f}  "
      f"gate_would_fire(frac>0.02): {(om_window>0.02).mean():.1%}")

# ── Summary & v41 recommendation ─────────────────────────────────────────
print(f"\n{'='*80}")
print(f"  SUMMARY:")
print(f"  ρ_typ={rho_typ:.4f}  gate thresholds: α=0.5→{0.5*rho_typ:.4f}  α=0.75→{0.75*rho_typ:.4f}")
print(f"  All ρ_eff at halt: {[round(v,2) for v in rho_halt_log]}")
n_shock  = len([v for v in rho_halt_log if v < 0.5 * rho_typ])
n_over   = len([v for v in rho_halt_log if v > 3.0 * rho_typ])
print(f"  ODE-shock trips (ρ < α=0.5): {n_shock} / {len(rho_halt_log)}")
print(f"  Overheated trips (ρ > 3×typ): {n_over} / {len(rho_halt_log)}")
print(f"  MaxDD is in normal-trading period")
print(f"  → ρ_eff gates (Fix 3 and variants) CANNOT reduce MaxDD")
print(f"  → Next candidate: post-CB re-entry ramp OR tighter CB threshold")
print("=" * 80)
