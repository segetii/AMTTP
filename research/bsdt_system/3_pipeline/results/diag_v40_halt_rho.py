# -*- coding: utf-8 -*-
"""
diag_v40_halt_rho.py
--------------------
Standalone diagnostic: re-runs the BEST v40 config (d=0.25, q=0.5, km=None,
no gates) and prints:
  - rho_eff at each CB halt bar
  - equity drop per CB trip
  - MaxDD event attribution (test window)
"""
import sys, pathlib, time, warnings
warnings.filterwarnings("ignore")

# ── import v40 module WITHOUT running main() ───────────────────────────────
SCRIPT_DIR = pathlib.Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

# When imported (not run as __main__), the v40 module's
# `if __name__ == "__main__": main()` guard prevents the sweep from running.
import run_crypto_godmode_v40_rho_halt as v40

import numpy as np
import pandas as pd

print("=" * 80)
print("  DIAGNOSTIC: rho_eff at CB halt times (best v40 config)")
print("=" * 80)

# ── Rebuild data (caches make this fast) ──────────────────────────────────
print("\n[1] Loading market data ...")
t0 = time.time()
from run_crypto_pairs_v34_full_combined import (
    OUT_DIR, TEST_START, TRAIN_START, build_1h_df,
)
df, _ = build_1h_df(start="2021-01-01", end="2026-06-01")
train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
test_mask  = np.asarray(df.index >= TEST_START)
test_ts    = pd.Timestamp(TEST_START)
print(f"  done ({time.time()-t0:.1f}s)  shape={df.shape}")

# ── Best config: d=0.25, q=0.50, kappa_max=None ───────────────────────────
d, q, kappa_max = 0.25, 0.50, None

print(f"\n[2] Building Σ + ODE for d={d}, q={q}, km={kappa_max} ...")
w_star          = v40.build_w_star(df, W_TARGET=v40.W_TARGET_A1)
b_aligned       = v40.build_b_aligned(w_star)
factor_R        = v40.build_factor_returns(df)
Sigma_base, _, sdiag, bdiag = v40.build_sigma(factor_R, train_mask, df, d)
Sigma_cap, lam_g7 = (Sigma_base, 0.0) if kappa_max is None else \
                     v40.regularise_sigma_g7(Sigma_base, float(kappa_max))
_, rank_Ix = v40.fisher_weight_noise_sqrt(Sigma_cap)

theta = v40.theta_from(b_aligned, train_mask, Sigma_cap, bdiag["budget"], q)
print(f"  θ={theta:.5f}  rank_Ix={rank_Ix}")

log_ann, rho_typ = v40.run_godmode_det_v39(
    df, train_mask, test_mask, w_star, b_aligned,
    Sigma_cap, theta, kappa=v40.KAPPA_A,
    label=f"diag_d{d}_q{q}_km{kappa_max}",
)
print(f"  ρ_typ={rho_typ:.4f}  threshold(α=0.5)={0.5*rho_typ:.4f}  "
      f"threshold(α=0.75)={0.75*rho_typ:.4f}")

# ── Rebuild unit signal ────────────────────────────────────────────────────
print("\n[3] Rebuilding unit signal ...")
ohlc_map = {sym: v40.fetch_futures_ohlcv_symbol(sym) for _, sym, _, _ in v40.ASSETS}
ch       = v40.get_channel_series()
inputs_noq = v40.build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                    signal_kind="wstar", use_quadrant=False)
inputs_q   = v40.build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                    signal_kind="wstar", use_quadrant=True)
inputs     = v40.attach_q_hot(inputs_noq, inputs_q)
sig_map    = {a: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{a}")
              for a, _, _, idx in v40.ASSETS}
unit       = v40.v28.run_variant_v28(v40.REG_VARIANT, inputs, sig_map, log_ann)["unit"]

# Align ODE arrays to unit index
idx = unit.index
unit_normal = unit.reindex(idx, fill_value=0.0)
unit_crash  = unit.reindex(idx, fill_value=0.0)   # same for crash port
gamma_arr    = np.asarray(log_ann["gamma"  ].reindex(idx, fill_value=0.0))
rhs_norm_arr = np.asarray(log_ann["rhs_norm"].reindex(idx, fill_value=0.0))
rho_eff_arr  = np.asarray(log_ann["rho_eff" ].reindex(idx, fill_value=float(rho_typ)))

print(f"  unit length={len(unit)}  rho_eff range=[{rho_eff_arr.min():.3f}, "
      f"{rho_eff_arr.max():.3f}]  median={float(np.median(rho_eff_arr)):.3f}")

# ── Run CB simulation with halt-time logging ───────────────────────────────
print("\n[4] Running CB simulation (no gates, η=0) — logging halt events ...")
K_normal     = v40.K_NORMAL
K_crash      = 0.0          # crash port disabled
Y_FLOOR      = v40.DYN_Y_FLOOR
CB_HALT_V    = v40.CB_HALT
CB_RESUME_V  = v40.CB_RESUME
INIT_V       = v40.INIT

WINDOW_BARS = v40.CB_WINDOW * v40.HOURS_PER_DAY
N = len(unit_normal)

mono_dq: list  = []  # (idx, eq)
eq             = INIT_V
peak_alltime   = INIT_V
halted         = False
halt_start_bar = 0

eq_vals:    list[float] = []
cb_flags:   list[int]   = []
halt_events: list[dict] = []   # ← the diagnostic log

for bar_i in range(N):
    ur = float(unit_normal.iloc[bar_i])

    # sliding-window peak
    while mono_dq and mono_dq[0][0] <= bar_i - WINDOW_BARS:
        mono_dq.pop(0)
    while mono_dq and mono_dq[-1][1] <= eq:
        mono_dq.pop()
    mono_dq.append((bar_i, eq))
    roll_peak = mono_dq[0][1]

    dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
    cb_dd  = max(0.0, 1.0 - eq / max(roll_peak,    1e-12))

    # halt trigger
    if not halted and cb_dd >= CB_HALT_V:
        halted         = True
        halt_start_bar = bar_i
        halt_events.append({
            "halt_bar":       bar_i,
            "halt_ts":        str(idx[bar_i]),
            "rho_eff_at_halt": float(rho_eff_arr[bar_i]),
            "cb_dd_at_halt":   float(cb_dd),
            "eq_at_halt":      float(eq),
        })

    # resume (no gates)
    elif halted and cb_dd <= CB_RESUME_V:
        # mark release equity
        halt_events[-1]["resume_bar"]      = bar_i
        halt_events[-1]["resume_ts"]       = str(idx[bar_i])
        halt_events[-1]["rho_eff_at_res"]  = float(rho_eff_arr[bar_i])
        halt_events[-1]["lock_bars"]       = bar_i - halt_start_bar
        halt_events[-1]["eq_at_resume"]    = float(eq)
        halted = False

    # equity step
    if not halted:
        y = max(-K_normal * ur, Y_FLOOR) if ur < 0 else K_normal * ur
        eq = max(eq * (1.0 + y * ur), 0.0)
    peak_alltime = max(peak_alltime, eq)
    eq_vals.append(eq)
    cb_flags.append(1 if halted else 0)

# build equity series
eqs = pd.Series(eq_vals, index=idx[:N])
eq_test = eqs[eqs.index >= test_ts]
rets    = eq_test.pct_change().dropna()
rolls   = eq_test.cummax()
dd_s    = (eq_test - rolls) / rolls
max_dd  = float(dd_s.min())
maxdd_ts = str(dd_s.idxmin())

print(f"\n  Total CB trips: {len(halt_events)}")
print(f"  MaxDD (test):   {max_dd:.1%}  at {maxdd_ts}")
print(f"  Threshold (α=0.5): {0.5*rho_typ:.4f}    (α=0.75): {0.75*rho_typ:.4f}"
      f"    (α=1.0): {rho_typ:.4f}")

# ── Print per-trip diagnostic ──────────────────────────────────────────────
print("\n" + "─"*100)
print(f"  {'#':>2}  {'Halt time':19}  {'ρ_eff_halt':>10}  {'ρ_eff_res':>10}  "
      f"{'lock_bars':>9}  {'eq_halt':>10}  {'eq_res':>10}  in_test")
print("─"*100)
for i, ev in enumerate(halt_events):
    ts     = ev["halt_ts"][:19]
    rh     = ev["rho_eff_at_halt"]
    rr     = ev.get("rho_eff_at_res", float("nan"))
    lb     = ev.get("lock_bars", -1)
    eqh    = ev["eq_at_halt"]
    eqr    = ev.get("eq_at_resume", float("nan"))
    intest = "✓" if ev["halt_ts"] >= v40.TEST_START else ""
    flag_s = " ← SHOCK" if rh < 0.5 * rho_typ else \
             " ← mild"  if rh < 0.75 * rho_typ else ""
    print(f"  {i+1:>2}  {ts}  {rh:>10.3f}  {rr:>10.3f}  {lb:>9}  "
          f"{eqh:>10.0f}  {eqr:>10.0f}  {intest:>7}{flag_s}")

# Mark which trip contains the MaxDD event
print("\n  MaxDD event analysis:")
maxdd_bar = int(eqs[eqs.index >= test_ts].index.get_loc(pd.Timestamp(maxdd_ts))
               + np.searchsorted(idx, pd.Timestamp(TEST_START)))
print(f"  MaxDD bar={maxdd_bar}  ts={maxdd_ts}")
mc = [i for i, ev in enumerate(halt_events)
      if ev.get("halt_bar", -1) <= maxdd_bar <= ev.get("resume_bar", maxdd_bar+1)]
if mc:
    ev = halt_events[mc[0]]
    print(f"  MaxDD falls inside trip #{mc[0]+1}: halt={ev['halt_ts'][:19]}  "
          f"ρ_eff_at_halt={ev['rho_eff_at_halt']:.4f}")
else:
    print("  MaxDD is OUTSIDE any CB trip — drawdown occurred during normal trading!")

# ── Summary ───────────────────────────────────────────────────────────────
in_test   = [ev for ev in halt_events if ev["halt_ts"] >= TEST_START]
rho_halts = [ev["rho_eff_at_halt"] for ev in in_test]
print(f"\n  In-test trips: {len(in_test)}")
if rho_halts:
    print(f"  ρ_eff at halt:  min={min(rho_halts):.4f}  "
          f"median={sorted(rho_halts)[len(rho_halts)//2]:.4f}  "
          f"max={max(rho_halts):.4f}")
    print(f"  α needed to gate WORST trip:  "
          f"{min(rho_halts)/rho_typ:.3f}×ρ_typ = {min(rho_halts)/rho_typ:.3f}")

print("=" * 80)
