"""
v38_mode2_investigation.py
===========================
Investigates Mode 2 crashes (ODE fully converged, pure regime shift).

Key findings:
1.  The deterministic gamma formula  γ*(X) = E/(E+θ)  → 0 as E → 0.
    From the stochastic Itô theorem, the correct stochastic formula is:
        γ*_stoch(X) = (E + c_Ito) / (E + c_Ito + θ)
    where  c_Ito = η · rank(I_X) / ρ_eff  (stochastic energy floor).

2.  The c_sigma_per_bar formula drops the ρ denominator:
    Code:    c_σ = η · DT · rank_Ix             (linear approximation)
    Correct: E_∞ = η · rank_Ix / ρ_eff          (asymptotic floor)
    Full:    budget(T) = E_∞ · (1 − e^{−ρ·T})  (saturates, not unbounded)

3.  rho_eff (the local convergence rate) is logged but NEVER used in the
    CB override or γ computation.  It IS what the theory requires.

This script:
  (a) Extracts per-bar ODE state for the Mode 2 segment (38a C1, Feb 2026)
  (b) Compares to Mode 1 (reversal) and Winner (C3) for the same initial
      ODE state (Ω ≈ 0)
  (c) Computes the stochastic γ correction and demonstrates its effect
"""
import sys
import time
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from v38_trade_clustering import (
    simulate_extended, VARIANTS,
    build_1h_df, TEST_START,
    DT, CB_HALT, CB_RESUME, CB_WINDOW,
    DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
    c_sigma_per_bar,
)
from run_crypto_godmode_v38_ito_tightcb import (
    fisher_weight_noise_sqrt, regularise_sigma_g7,
    build_sigma, theta_from, run_godmode_det,
    K_NORMAL, KAPPA_CAP, CB_HALT as CB_HALT_,
)
from run_crypto_pairs_v34_full_combined import (
    TEST_START, TRAIN_START, build_1h_df,
)
from run_crypto_godmode_v1 import (
    KAPPA_A, W_TARGET_A1, build_b_aligned, build_w_star,
    _predictive_scalars, CONV_MIN, CONV_MAX, W_BOX,
    ANNEAL_AMP, ANNEAL_PEAK, TradingDomain, EPSILON, N_STATE, A_FACTORS,
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
)
from run_crypto_godmode_v35_top5_cb_transition import (
    ffd_weights, frac_diff_series, ffd_covariance,
    build_sigma, theta_from,
    TOP5, REG_VARIANT, FFD_THRESHOLD, FFD_MAX_LAG,
    K_NORMAL, RT_BPS, KAPPA_CAP,
)
import run_crypto_godmode_v27_all_microstructure as v27
import run_crypto_godmode_v28_canonical_stability as v28


OMEGA_THRESH = 0.02   # Mode-1 filter threshold


def run_analysis():
    print("=" * 75)
    print("  MODE 2 INVESTIGATION — Stochastic γ* and rho_eff study")
    print("=" * 75)

    # ── [0] Load data ─────────────────────────────────────────────────────────
    print("\n[0] Loading data...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        ms = v27._get_ms(sym)
        print(f"  {sym}: {ms.shape}")

    df, _      = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask  = np.asarray(df.index >= TEST_START)
    test_ts    = pd.Timestamp(TEST_START)
    w_star     = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned  = build_b_aligned(w_star)
    factor_R   = build_factor_returns(df)
    v27.RT_COST = RT_BPS / 10_000.0

    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol)
                for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()

    var = VARIANTS[0]   # 38a
    d, q, eta, lock_min = var["d"], var["q"], var["eta"], var["lock_min"]
    kappa_max = var.get("kappa_max")

    # ── [1] Sigma + ODE log ───────────────────────────────────────────────────
    print("\n[1] Building sigma and running ODE...")
    Sigma_base, Sigma_ffd, sdiag, bdiag = build_sigma(factor_R, train_mask, df, d)
    if kappa_max is not None:
        Sigma_cap, lam_g7 = regularise_sigma_g7(Sigma_base, float(kappa_max))
    else:
        Sigma_cap = Sigma_base; lam_g7 = 0.0
    _, rank_Ix = fisher_weight_noise_sqrt(Sigma_cap)
    c_sb       = c_sigma_per_bar(eta, rank_Ix)
    theta      = theta_from(b_aligned, train_mask, Sigma_cap, bdiag["budget"], q)

    print(f"  θ={theta:.5f}  rank_Ix={rank_Ix}  η={eta:.2e}  c_σ/bar={c_sb:.3e}")

    label  = f"v38a_d{str(d).replace('.','p')}_q{str(q).replace('.','p')}"
    ode_log = run_godmode_det(
        df, train_mask, test_mask, w_star, b_aligned,
        Sigma_cap, theta, kappa=KAPPA_A, label=label,
    )

    # rho_typ = training-median rho_eff
    train_rho = ode_log.loc[df.index[train_mask], "rho_eff"]
    rho_typ   = float(train_rho[train_rho > 0].median()) if (train_rho > 0).any() else 1.0
    print(f"  rho_typ (train median) = {rho_typ:.4f}")

    # ── [2] Extended CB simulation ────────────────────────────────────────────
    print("\n[2] Running extended CB simulation...")
    inputs_noq = build_asset_inputs(df, ode_log, w_star, ch, ohlc_map,
                                    signal_kind="wstar", use_quadrant=False)
    inputs_q   = build_asset_inputs(df, ode_log, w_star, ch, ohlc_map,
                                    signal_kind="wstar", use_quadrant=True)
    inputs     = attach_q_hot(inputs_noq, inputs_q)
    sig_map    = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}")
                  for asset, _, _, idx in ASSETS}
    run_out    = v28.run_variant_v28(REG_VARIANT, inputs, sig_map, ode_log)
    unit       = run_out["unit"]
    unit_crash = pd.Series(0.0, index=unit.index)

    from v38_trade_clustering import simulate_extended
    sim = simulate_extended(
        unit_normal     = unit,
        unit_crash      = unit_crash,
        K_normal        = K_NORMAL,
        K_crash         = 0.0,
        dd_soft         = DYN_DD_SOFT,
        dd_stop         = DYN_DD_STOP,
        y_floor         = DYN_Y_FLOOR,
        cb_halt         = CB_HALT,
        cb_resume       = CB_RESUME,
        cb_window_days  = CB_WINDOW,
        ito_c_sigma_bar = c_sb,
        lock_min        = lock_min,
    )

    ode_log = ode_log.reindex(sim["cb_flag"].index, method="ffill")
    cb_flag = sim["cb_flag"]
    rets    = sim["rets"]
    eq      = sim["eq"]

    test_cb   = cb_flag[cb_flag.index >= test_ts]
    test_rets = rets[rets.index >= test_ts]
    test_ode  = ode_log.reindex(test_cb.index, method="ffill")
    test_eq   = eq[eq.index >= test_ts]
    active    = (test_cb == 0)
    arr       = active.values
    idx       = active.index

    # ── [3] Identify all test segments ────────────────────────────────────────
    print("\n[3] Identifying test segments...")
    segs = []
    in_seg = False
    for i in range(len(arr)):
        if arr[i] and not in_seg:
            in_seg = True; seg_s = i
        elif (not arr[i] or i == len(arr) - 1) and in_seg:
            seg_e = i if not arr[i] else i + 1
            in_seg = False
            seg_rets = test_rets.iloc[seg_s:seg_e]
            seg_ode  = test_ode.iloc[seg_s:seg_e]
            if len(seg_rets) < 4:
                continue
            start_ts  = idx[seg_s]
            omega     = float(seg_ode.iloc[0]["gamma"]) * float(seg_ode.iloc[0]["rhs_norm"])
            tot_pnl   = float(seg_rets.sum())
            segs.append(dict(
                seg_s     = seg_s,
                seg_e     = seg_e,
                start     = start_ts,
                n         = seg_e - seg_s,
                omega     = omega,
                total_pnl = tot_pnl,
                label     = "WIN" if tot_pnl > 0 else "LOSE",
                # ODE state AT ENTRY
                E_start        = float(seg_ode.iloc[0]["E"]),
                gamma_start    = float(seg_ode.iloc[0]["gamma"]),
                rhs_start      = float(seg_ode.iloc[0]["rhs_norm"]),
                rho_start      = float(seg_ode.iloc[0]["rho_eff"]),
                mfls_start     = float(seg_ode.iloc[0]["mfls"]),
                vE_start       = float(seg_ode.iloc[0]["v_E"]),
                dEdt_start     = float(seg_ode.iloc[0]["dE_dt"]),
                cos_th_start   = float(seg_ode.iloc[0]["cos_theta"]),
                stale_start    = float(seg_ode.iloc[0]["stale_flag"]),
                drift_start    = float(seg_ode.iloc[0]["drift_flag"]),
                theta_t_start  = float(seg_ode.iloc[0]["theta_t"]),
                # ODE mean over segment
                rho_mean       = float(seg_ode["rho_eff"].mean()),
                rho_min        = float(seg_ode["rho_eff"].min()),
                stale_mean     = float(seg_ode["stale_flag"].mean()),
                drift_mean     = float(seg_ode["drift_flag"].mean()),
            ))

    # ── [4] Print per-segment comparison table ────────────────────────────────
    print(f"\n  {'Start':20s}  {'n':>4s}  {'Total':>8s}  {'Omega':>7s}  {'E_s':>7s}  {'rho_s':>8s}  {'vE_s':>8s}  {'dEdt_s':>8s}  {'stale':>5s}  {'drift':>5s}  Label  Mode")
    print("  " + "-" * 110)
    for s in segs:
        mode = ""
        if s["omega"] >= OMEGA_THRESH:
            mode = "M1-BLOCK"
        elif s["label"] == "LOSE":
            mode = "M2-CRASH"
        else:
            mode = "WINNER"
        print(f"  {str(s['start']):20s}  {s['n']:>4d}  {s['total_pnl']:>+8.4f}  "
              f"{s['omega']:>7.5f}  {s['E_start']:>7.5f}  "
              f"{s['rho_start']:>8.4f}  {s['vE_start']:>+8.4f}  "
              f"{s['dEdt_start']:>+8.4f}  {s['stale_start']:>5.0f}  "
              f"{s['drift_start']:>5.0f}  {s['label']:5s}  {mode}")

    # ── [5] Stochastic γ correction formula ───────────────────────────────────
    print(f"\n{'='*75}")
    print("  STOCHASTIC γ* CORRECTION (from Theorem thm:sde-bound)")
    print(f"{'='*75}")
    print()
    print("  Deterministic formula (implemented):   γ*(X) = E / (E + θ)")
    print("  Stochastic formula (MISSING):          γ*_s(X) = (E + c_Ito) / (E + c_Ito + θ)")
    print()
    print("  c_Ito = η · rank(I_X) / ρ_eff   [stochastic energy floor, Theorem thm:sde-bound]")
    print()
    print(f"  η          = {eta:.2e}")
    print(f"  rank(I_X)  = {rank_Ix}")
    print(f"  ρ_typ      = {rho_typ:.4f}")
    c_ito = eta * rank_Ix / rho_typ
    print(f"  c_Ito      = {c_ito:.6f}  [E_∞ = η·rank/ρ]")
    print()
    # Compare γ* for various E values
    for E_test in [0.0, 1e-5, c_ito*0.1, c_ito, 0.01, 0.1]:
        gam_det   = E_test / (E_test + theta) if (E_test + theta) > 0 else 0.0
        gam_stoch = (E_test + c_ito) / (E_test + c_ito + theta)
        print(f"    E={E_test:.2e}  γ*_det={gam_det:.5f}  γ*_stoch={gam_stoch:.5f}"
              f"  delta_γ={gam_stoch-gam_det:+.5f}  "
              f"{'<-- Mode 2 entry' if abs(E_test) < 1e-4 else ''}")

    print()
    print("  MODE 2 FILTER: require γ*_stoch(X_entry) > γ_min")
    print("  Or equivalently: c_Ito > threshold  →  re-entry not allowed when rho_eff too small")
    print()

    # ── [6] Noise budget formula comparison ───────────────────────────────────
    print(f"{'='*75}")
    print("  c_sigma_per_bar FORMULA ANALYSIS (math error)")
    print(f"{'='*75}")
    print()
    print("  G2.4 noise budget in code:")
    print(f"    noise_budget = c_σ × lock_bars = η·DT·rank_Ix × lock_bars  (LINEAR, UNBOUNDED)")
    print()
    print("  Correct formula from Theorem thm:sde-bound:")
    print(f"    E_∞ = η·rank_Ix / ρ_eff                                     (CONSTANT)")
    print(f"    budget(T) = E_∞ × (1 - exp(-ρ_eff·T))                       (SATURATING)")
    print()
    for lock_bars in [100, 500, 1000, 5000, 10000]:
        T_lock = lock_bars * DT   # in years
        budget_linear = c_sb * lock_bars
        budget_correct = c_ito * (1 - np.exp(-rho_typ * T_lock))
        budget_correct_inf = c_ito   # asymptotic floor
        ratio = budget_linear / max(budget_correct, 1e-15) if budget_correct > 0 else float('inf')
        print(f"    lock={lock_bars:>6d}h  linear={budget_linear:.4e}  "
              f"correct={budget_correct:.4e}  ratio={ratio:.2f}x"
              f"{'  *** OVERFLOW risk' if ratio > 10 else ''}")
    print()
    print(f"  Asymptotic correct budget (E_∞) = {c_ito:.4e}")
    print(f"  Code's budget after 10000h     = {c_sb * 10000:.4e}")
    print(f"  Unlimited linear growth        = {(c_sb * 100000):.4e}  (meaningless beyond E_∞)")

    # ── [7] Mode 2 detection rule ─────────────────────────────────────────────
    print(f"\n{'='*75}")
    print("  MODE 2 DETECTION RULE")
    print(f"{'='*75}")
    mode2 = [s for s in segs if s["label"] == "LOSE" and s["omega"] < OMEGA_THRESH]
    mode1 = [s for s in segs if s["omega"] >= OMEGA_THRESH]
    winners = [s for s in segs if s["label"] == "WIN"]
    print(f"\n  Segments: Mode1={len(mode1)}  Mode2={len(mode2)}  Winners={len(winners)}")
    print()
    if mode2:
        print("  Mode 2 segments (all with Ω<0.02, LOSE):")
        for s in mode2:
            # Compute stochastic γ floor at entry
            rho_entry = s["rho_start"]
            if rho_entry > 0:
                c_ito_local = eta * rank_Ix / rho_entry
            else:
                c_ito_local = eta * rank_Ix / max(rho_typ * 0.01, 1e-8)  # floor
            gam_s = (s["E_start"] + c_ito_local) / (s["E_start"] + c_ito_local + theta)
            print(f"    {str(s['start']):20s}  n={s['n']:>4d}  pnl={s['total_pnl']:+.3f}")
            print(f"      ODE: E={s['E_start']:.4e}  rho_eff={s['rho_start']:.4f}"
                  f"  vE={s['vE_start']:+.4e}  dEdt={s['dEdt_start']:+.4e}")
            print(f"      stale={s['stale_start']:.0f}  drift={s['drift_start']:.0f}"
                  f"  c_Ito_local={c_ito_local:.4e}  γ*_stoch={gam_s:.5f}")
    print()
    if winners:
        print("  Winner segments (Ω<0.02, WIN):")
        for s in winners:
            rho_entry = s["rho_start"]
            if rho_entry > 0:
                c_ito_local = eta * rank_Ix / rho_entry
            else:
                c_ito_local = eta * rank_Ix / max(rho_typ * 0.01, 1e-8)
            gam_s = (s["E_start"] + c_ito_local) / (s["E_start"] + c_ito_local + theta)
            print(f"    {str(s['start']):20s}  n={s['n']:>4d}  pnl={s['total_pnl']:+.3f}")
            print(f"      ODE: E={s['E_start']:.4e}  rho_eff={s['rho_start']:.4f}"
                  f"  vE={s['vE_start']:+.4e}  dEdt={s['dEdt_start']:+.4e}")
            print(f"      stale={s['stale_start']:.0f}  drift={s['drift_start']:.0f}"
                  f"  c_Ito_local={c_ito_local:.4e}  γ*_stoch={gam_s:.5f}")
    print()
    print("  SUMMARY:")
    print("  Mode 2 cannot be separated from Winners by Ω alone.")
    print("  The stochastic γ correction uses c_Ito = η·rank/ρ_eff:")
    print("    → Small ρ_eff at entry = large c_Ito = larger stochastic floor")
    print("    → Larger γ*_stoch (more friction) even at E≈0")
    print("    → This is the variable missing from the deterministic formula")


if __name__ == "__main__":
    t0 = time.time()
    run_analysis()
    print(f"\nDone in {time.time()-t0:.0f}s")
