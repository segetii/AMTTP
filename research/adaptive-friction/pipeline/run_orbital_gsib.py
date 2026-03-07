"""
run_orbital_gsib.py
===================
Second-order (orbital) Newtonian simulation on REAL World Bank + FDIC data.

Compares three dynamics:
  1. Molecular-only (first-order, no gravity)
  2. Molecular+Gravity first-order (gradient descent → collapse → 92% Ponzi)
  3. Molecular+Gravity SECOND-ORDER (velocity-Verlet → stable orbits)

Key question: Does angular momentum conservation fix the Minsky classification?

All parameters data-derived. Zero heuristics.
"""
from __future__ import annotations
import sys, time
import numpy as np
import pandas as pd
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

THIS_DIR = Path(__file__).parent
BL_DIR   = THIS_DIR.parent / "banklevel_enhanced"
for p in [str(THIS_DIR), str(BL_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from gsib_loader_real import build_gsib_panel_real, FEATURE_NAMES
import gravity_engine as mol_engine
import gravity_engine_newtonian as newton_engine
from gravity_engine_newtonian import compute_masses_from_data, compute_G_from_data
from gravity_engine_orbital import (
    compute_damping_from_data, compute_initial_velocities,
    angular_momentum, total_angular_momentum, kinetic_energy,
    simulate_orbital, analyse_trajectory_orbital,
    BSDTOperator, total_force, total_energy, newtonian_energy,
)

NORMAL_START = "2005-03-31"
NORMAL_END   = "2006-12-31"

CRISIS_DATES = {
    "GFC 2008":           "2008-09-30",
    "Nigeria Reform 2009":"2009-09-30",
    "European Debt 2011": "2011-09-30",
    "Nigeria Recess 2016":"2016-06-30",
    "COVID 2020":         "2020-03-31",
    "Rate Shock 2022":    "2022-09-30",
}


def classify_minsky(cos_arr):
    """Classify Minsky regimes: cos > 0 = hedge, < -0.3 = Ponzi, between = speculative."""
    hedge  = np.sum(cos_arr > 0.0) / len(cos_arr)
    ponzi  = np.sum(cos_arr < -0.3) / len(cos_arr)
    spec   = 1.0 - hedge - ponzi
    return hedge, spec, ponzi


def main():
    t_start = time.perf_counter()
    print("=" * 80)
    print("  ORBITAL DYNAMICS — Second-Order Newtonian Simulation")
    print("  Angular momentum conservation.  Velocity-Verlet integrator.")
    print("  Real World Bank + FDIC G-SIB data.  Zero heuristics.")
    print("=" * 80)

    # ── 1. Load data ──
    print("\n[1/6] Loading real G-SIB panel...")
    panel = build_gsib_panel_real(
        quarters_start="2005-01-01", quarters_end="2023-12-31",
        force_refresh=False, min_coverage=0.50, verbose=False)
    X_raw = panel["X"]
    dates = panel["dates"]
    meta  = panel["meta"]
    T, N, d = X_raw.shape

    norm_mask = (dates >= pd.Timestamp(NORMAL_START)) & \
                (dates <= pd.Timestamp(NORMAL_END))
    if norm_mask.sum() < 4:
        norm_mask[:8] = True
    X_ref = X_raw[norm_mask]
    mu_ref = X_ref.reshape(-1, d).mean(axis=0)
    sd_ref = X_ref.reshape(-1, d).std(axis=0) + 1e-9
    X_std = (X_raw - mu_ref) / sd_ref
    mu_eq = X_std[norm_mask].reshape(-1, d).mean(axis=0)

    names = [m["name"] for m in meta]
    regions = [m["region"] for m in meta]
    print(f"  Panel: T={T}, N={N}, d={d}")

    # ── 2. Data-derived parameters ──
    print("\n[2/6] Deriving all parameters from data...")
    masses = compute_masses_from_data(X_std, method="energy")
    G_data = compute_G_from_data(X_std, masses)
    beta   = compute_damping_from_data(X_std, masses, G=G_data)

    print(f"  G (data-derived) = {G_data:.6f}")
    print(f"  beta (data-derived damping) = {beta:.6f}")
    print(f"  Mass range: [{masses.min():.3f}, {masses.max():.3f}], "
          f"ratio = {masses.max()/masses.min():.1f}x")

    # Kepler orbital period for reference
    mean_r = 0.0
    count = 0
    for t in range(0, T, max(1, T // 20)):
        X = X_std[t]
        diff = X[:, None, :] - X[None, :, :]
        dist = np.sqrt(np.sum(diff ** 2, axis=2) + 1e-12)
        triu = np.triu_indices(N, k=1)
        mean_r += dist[triu].mean()
        count += 1
    mean_r /= count
    tau_orb = 2 * np.pi * np.sqrt(mean_r ** 3 / (G_data * masses.mean() + 1e-12))
    print(f"  Mean inter-bank distance = {mean_r:.4f}")
    print(f"  Orbital period (Kepler) = {tau_orb:.2f} timesteps")
    print(f"  Damping timescale = {1/beta:.2f} timesteps")

    # ── 3. Fit BSDT ──
    print("\n[3/6] Fitting BSDT operators...")
    X_normal = X_std[norm_mask]
    bsdt = BSDTOperator().fit(X_normal)
    bsdt_mol = mol_engine.BSDTOperator().fit(X_normal)

    # ── 4. Crisis simulations: 3 dynamics compared ──
    print("\n[4/6] Crisis simulations — 3 dynamics compared...")
    print()
    print("=" * 100)
    print(f"{'Crisis':>20s} | {'Dynamics':>12s} | {'mean cos':>9s} | "
          f"{'frac>0':>6s} | {'E_pot':>10s} | {'E_kin':>10s} | {'L_total':>10s} | {'MFLS':>8s}")
    print("-" * 100)

    crisis_results = {}

    for crisis_name, crisis_date in CRISIS_DATES.items():
        ts = pd.Timestamp(crisis_date)
        idx = int(np.argmin(np.abs(dates - ts)))
        X_crisis = X_std[idx]
        mu_t = X_crisis.mean(axis=0)

        # Data-derived initial velocity
        if idx > 0:
            V0 = X_std[idx] - X_std[idx - 1]
        else:
            V0 = np.zeros_like(X_crisis)

        crisis_results[crisis_name] = {}

        # --- A. Molecular-only (1st order) ---
        dyn_mol = mol_engine.simulate_and_align(
            X_crisis, mu_eq, bsdt_mol, n_steps=100, eta=0.02)
        E_mol = mol_engine.total_energy(X_crisis, mu_eq)
        mfls_mol = bsdt.mfls_score(X_crisis)

        crisis_results[crisis_name]["molecular"] = dyn_mol
        print(f"{crisis_name:>20s} | {'Mol (1st)':>12s} | {dyn_mol['mean_cos']:>+9.4f} | "
              f"{dyn_mol['frac_above_07']*100:>5.1f}% | {E_mol:>+10.2f} | {'N/A':>10s} | "
              f"{'N/A':>10s} | {mfls_mol:>8.1f}")

        # --- B. Gravity first-order (gradient descent → collapse) ---
        dyn_1st = newton_engine.simulate_and_align(
            X_crisis, mu_eq, bsdt, masses=masses, mix_grav=1.0,
            n_steps=100, eta=0.02, G=G_data)
        E_1st = total_energy(X_crisis, mu_eq, masses=masses, mix_grav=1.0, G=G_data)

        crisis_results[crisis_name]["gravity_1st"] = dyn_1st
        print(f"{'':>20s} | {'Grav (1st)':>12s} | {dyn_1st['mean_cos']:>+9.4f} | "
              f"{dyn_1st['frac_above_07']*100:>5.1f}% | {E_1st:>+10.2f} | {'N/A':>10s} | "
              f"{'N/A':>10s} | {mfls_mol:>8.1f}")

        # --- C. Gravity second-order (orbital → angular momentum) ---
        dyn_2nd = simulate_orbital(
            X_crisis, V0, mu_eq, bsdt, masses,
            beta=beta, mix_grav=1.0, n_steps=200, dt=0.01, G=G_data)

        E_pot_2nd = dyn_2nd["energy"][-1]
        E_kin_2nd = dyn_2nd["kinetic"][-1]
        L_2nd = dyn_2nd["angular_mom"][-1]
        mfls_2nd = dyn_2nd["mfls"][-1]

        crisis_results[crisis_name]["gravity_2nd"] = dyn_2nd
        frac_pos = float((dyn_2nd["cos_history"] > 0).mean())
        print(f"{'':>20s} | {'Orb (2nd)':>12s} | {dyn_2nd['mean_cos']:>+9.4f} | "
              f"{frac_pos*100:>5.1f}% | {E_pot_2nd:>+10.2f} | {E_kin_2nd:>+10.2f} | "
              f"{L_2nd:>10.2f} | {mfls_2nd:>8.1f}")

        print("-" * 100)

    # ── 5. Full trajectory: 2nd-order analysis ──
    print("\n[5/6] Full trajectory analysis (2nd-order orbital)...")
    stats_2nd = analyse_trajectory_orbital(
        X_std, mu_eq, bsdt, masses, beta,
        mix_grav=1.0, alpha=newton_engine.ALPHA,
        verbose=True, G=G_data)

    # Also get 1st-order stats for comparison
    bsdt_newton = newton_engine.BSDTOperator().fit(X_normal)
    stats_1st = newton_engine.analyse_trajectory(
        X_std, mu_eq, bsdt_newton, masses=masses, mix_grav=1.0,
        alpha=newton_engine.ALPHA, n_power_iter=10, verbose=False, G=G_data)

    stats_mol = mol_engine.analyse_trajectory(
        X_std, mu_eq, bsdt_mol, alpha=mol_engine.ALPHA,
        n_power_iter=10, verbose=False)

    # ── 6. The big comparison ──
    print("\n[6/6] Three-way comparison...")

    print(f"\n  {'Metric':>30s} | {'Molecular':>12s} | {'Grav 1st':>12s} | {'Orbital 2nd':>12s}")
    print("  " + "-" * 75)

    comparisons = [
        ("Mean cos theta",      stats_mol["cos_theta"].mean(),
                                stats_1st["cos_theta"].mean(),
                                stats_2nd["cos_theta"].mean()),
        ("Mean MFLS",           stats_mol["mfls"].mean(),
                                stats_1st["mfls"].mean(),
                                stats_2nd["mfls"].mean()),
        ("Mean |F|",            stats_mol["force_norm"].mean(),
                                stats_1st["force_norm"].mean(),
                                stats_2nd["force_norm"].mean()),
        ("Mean E_potential",    stats_mol["energy"].mean(),
                                stats_1st["energy"].mean(),
                                stats_2nd["energy"].mean()),
        ("Mean E_kinetic",      0.0,  0.0,
                                stats_2nd["kinetic_energy"].mean()),
        ("Mean L (ang mom)",    0.0,  0.0,
                                stats_2nd["angular_momentum"].mean()),
        ("Mean virial ratio",   0.0,  0.0,
                                stats_2nd["virial_ratio"].mean()),
    ]

    for name, v_mol, v_1st, v_2nd in comparisons:
        print(f"  {name:>30s} | {v_mol:>+12.4f} | {v_1st:>+12.4f} | {v_2nd:>+12.4f}")

    # ── Minsky classification ──
    print("\n  MINSKY REGIME CLASSIFICATION:")
    print(f"  {'':>12s}  {'Hedge':>8s}  {'Speculative':>12s}  {'Ponzi':>8s}")

    h_mol, s_mol, p_mol = classify_minsky(stats_mol["cos_theta"])
    h_1st, s_1st, p_1st = classify_minsky(stats_1st["cos_theta"])
    h_2nd, s_2nd, p_2nd = classify_minsky(stats_2nd["cos_theta"])

    print(f"  {'Molecular':>12s}  {h_mol*100:>7.1f}%  {s_mol*100:>11.1f}%  {p_mol*100:>7.1f}%")
    print(f"  {'Grav 1st':>12s}  {h_1st*100:>7.1f}%  {s_1st*100:>11.1f}%  {p_1st*100:>7.1f}%")
    print(f"  {'Orbital 2nd':>12s}  {h_2nd*100:>7.1f}%  {s_2nd*100:>11.1f}%  {p_2nd*100:>7.1f}%")

    # ── Angular momentum conservation check ──
    print("\n  ANGULAR MOMENTUM CONSERVATION:")
    L = stats_2nd["angular_momentum"]
    L_init = L[1] if len(L) > 1 else L[0]  # skip t=0 (V=0)
    L_mean = L[1:].mean()
    L_std  = L[1:].std()
    L_var_coeff = L_std / (L_mean + 1e-12)
    print(f"    L(t=1)  = {L_init:.4f}")
    print(f"    L(mean) = {L_mean:.4f}")
    print(f"    L(std)  = {L_std:.4f}")
    print(f"    CV(L)   = {L_var_coeff:.4f}  "
          f"({'well conserved' if L_var_coeff < 0.1 else 'partially conserved' if L_var_coeff < 0.5 else 'not conserved'})")

    # ── Virial theorem check ──
    print("\n  VIRIAL THEOREM CHECK (2K/|U| should be ~1.0):")
    vr = stats_2nd["virial_ratio"]
    print(f"    Mean virial ratio = {vr.mean():.4f}")
    print(f"    Std virial ratio  = {vr.std():.4f}")
    virial_status = "virial equilibrium" if 0.5 < vr.mean() < 2.0 else "not virialised"
    print(f"    Status: {virial_status}")

    # ── Annual time series ──
    print("\n  ANNUAL TIME SERIES:")
    print(f"  {'Year':>6s}  {'cos_mol':>8s}  {'cos_1st':>8s}  {'cos_2nd':>8s}  "
          f"{'MFLS':>8s}  {'E_kin':>8s}  {'L_ang':>8s}  {'virial':>8s}")
    print("  " + "-" * 68)

    for y in range(2005, 2024):
        mask = np.array([d.year == y for d in dates])
        if mask.sum() == 0:
            continue
        print(f"  {y:>6d}  "
              f"{stats_mol['cos_theta'][mask].mean():>+8.4f}  "
              f"{stats_1st['cos_theta'][mask].mean():>+8.4f}  "
              f"{stats_2nd['cos_theta'][mask].mean():>+8.4f}  "
              f"{stats_2nd['mfls'][mask].mean():>8.1f}  "
              f"{stats_2nd['kinetic_energy'][mask].mean():>8.2f}  "
              f"{stats_2nd['angular_momentum'][mask].mean():>8.2f}  "
              f"{stats_2nd['virial_ratio'][mask].mean():>8.4f}")

    # ── Crisis-period breakdown ──
    print("\n  CRISIS-PERIOD BREAKDOWN:")
    print(f"  {'Period':>20s} | {'cos_mol':>8s} | {'cos_1st':>8s} | {'cos_2nd':>8s} | "
          f"{'MFLS':>8s} | {'L_ang':>8s} | {'virial':>8s}")
    print("  " + "-" * 80)

    for crisis_name, crisis_date in CRISIS_DATES.items():
        ts = pd.Timestamp(crisis_date)
        idx = int(np.argmin(np.abs(dates - ts)))
        lo, hi = max(0, idx - 4), min(T, idx + 5)
        print(f"  {crisis_name:>20s} | "
              f"{stats_mol['cos_theta'][lo:hi].mean():>+8.4f} | "
              f"{stats_1st['cos_theta'][lo:hi].mean():>+8.4f} | "
              f"{stats_2nd['cos_theta'][lo:hi].mean():>+8.4f} | "
              f"{stats_2nd['mfls'][lo:hi].mean():>8.1f} | "
              f"{stats_2nd['angular_momentum'][lo:hi].mean():>8.2f} | "
              f"{stats_2nd['virial_ratio'][lo:hi].mean():>8.4f}")

    # ── Summary ──
    print("\n" + "=" * 80)
    print("  SUMMARY — Does Angular Momentum Fix the Gravity Problem?")
    print("=" * 80)

    improved_minsky = (h_2nd > h_1st) or (p_2nd < p_1st)
    mfls_still_invariant = abs(stats_2nd["mfls"].mean() - stats_mol["mfls"].mean()) < 1.0

    print(f"""
  Three dynamics compared on {N} banks, {T} quarters:
    1. Molecular (1st-order): {h_mol*100:.0f}% hedge / {s_mol*100:.0f}% spec / {p_mol*100:.0f}% Ponzi
    2. Gravity 1st-order:     {h_1st*100:.0f}% hedge / {s_1st*100:.0f}% spec / {p_1st*100:.0f}% Ponzi
    3. Orbital 2nd-order:     {h_2nd*100:.0f}% hedge / {s_2nd*100:.0f}% spec / {p_2nd*100:.0f}% Ponzi

  Angular momentum: L_mean = {L_mean:.4f}, CV = {L_var_coeff:.4f}
  Virial ratio: {vr.mean():.4f} (target = 1.0)
  MFLS invariance: {'PRESERVED' if mfls_still_invariant else 'BROKEN'} (mean = {stats_2nd['mfls'].mean():.1f})

  Minsky discrimination {'IMPROVED' if improved_minsky else 'NOT IMPROVED'} vs 1st-order gravity
  MFLS crisis detection: {'STILL WORKS' if mfls_still_invariant else 'COMPROMISED'}
""")

    elapsed = time.perf_counter() - t_start
    print(f"  Total elapsed: {elapsed:.1f}s")
    print("  Done.")


if __name__ == "__main__":
    main()
