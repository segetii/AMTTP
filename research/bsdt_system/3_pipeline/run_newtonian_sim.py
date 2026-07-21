"""
run_newtonian_sim.py
====================
Simulate the Newtonian GravityEngine on real FRED economic data and compare
with the original molecular-only engine across 3 crisis periods.

Sector masses are assigned proportional to systemic importance:
    Large Commercial Banks  -> 5.0  (too big to fail)
    Shadow Banking          -> 3.0  (leveraged, systemic)
    Investment Banks        -> 2.5  (interconnected)
    GSEs                    -> 2.0  (Fannie/Freddie)
    REITs                   -> 1.5
    ...
    Credit Unions           -> 0.3  (small, local)

This creates gravitational hierarchy: large sectors pull small ones,
producing asymmetric contagion dynamics.
"""

from __future__ import annotations
import sys
import time
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fred_loader import fetch_all, apply_transforms, standardise
from state_matrix import build_state_matrix, get_normal_period, SECTOR_NAMES

# Import BOTH engines
import gravity_engine as mol_engine           # original molecular-only
import gravity_engine_newtonian as newton_engine  # molecular + gravity
from gravity_engine_newtonian import compute_masses_from_data, compute_G_from_data

CRISIS_DATES = {
    "GFC 2008":        "2008-09-30",
    "COVID 2020":      "2020-03-31",
    "Rate Shock 2022": "2022-09-30",
}

# No hand-tuned parameters — all derived from data


def load_fred_data(verbose=True):
    """Load and prepare FRED data exactly as the main pipeline does."""
    print("[1/4] Loading FRED data...")
    try:
        raw = fetch_all(use_cache=True, verbose=verbose)
    except Exception as e:
        print(f"  FRED fetch failed ({e}), using synthetic fallback.")
        from run_pipeline import _synthetic_fred_fallback
        raw = _synthetic_fred_fallback()

    xf  = apply_transforms(raw)
    std, mu_fred, sig_fred = standardise(xf)
    X_all, dates = build_state_matrix(std)
    T, N, d = X_all.shape
    print(f"  State matrix: T={T} quarters, N={N} sectors, d={d} features")
    print(f"  Date range: {dates[0].date()} → {dates[-1].date()}")

    # Normal period for BSDT
    X_normal = get_normal_period(X_all, dates)
    mu_eq = X_normal.reshape(-1, d).mean(axis=0)
    print(f"  Normal period: {X_normal.shape[0]} quarters (2002–2006)")
    return X_all, dates, X_normal, mu_eq


def derive_masses_and_G(X_all, verbose=True):
    """
    Compute masses and G entirely from the data.  Zero heuristics.
    """
    print("\n[2/4] Deriving masses and G from data (no heuristics)...")
    T, N, d = X_all.shape

    # Compute masses via all three methods for comparison
    methods = ["influence", "energy", "variance"]
    mass_results = {}
    for method in methods:
        m = compute_masses_from_data(X_all, method=method)
        mass_results[method] = m
        if verbose:
            print(f"\n  Method: {method}")
            ranked = np.argsort(-m)
            for rank, i in enumerate(ranked, 1):
                bar = '█' * int(m[i] * 6)
                print(f"    {rank:2d}. {SECTOR_NAMES[i]:28s}  m={m[i]:.3f}  {bar}")

    # Use "influence" as the primary method (measures systemic interconnectedness)
    masses = mass_results["influence"]

    # Compute G from the data's own scales
    G_data = compute_G_from_data(X_all, masses)
    if verbose:
        print(f"\n  Data-derived G = {G_data:.6f}")
        print(f"  (set so F_grav(⟨r⟩) ≈ α = {newton_engine.ALPHA})")
        mean_mm = (masses[:, None] * masses[None, :])[np.triu_indices(N, k=1)].mean()
        print(f"  Mean mass product ⟨mᵢmⱼ⟩ = {mean_mm:.4f}")

    return masses, G_data, mass_results


def run_crisis_comparison(X_all, dates, mu_eq, X_normal, masses, G_data):
    """Run both engines on each crisis and compare."""
    print("\n[3/4] Fitting BSDT operators...")

    bsdt_mol = mol_engine.BSDTOperator().fit(X_normal)
    bsdt_new = newton_engine.BSDTOperator().fit(X_normal)

    # mix_grav sweep: 0 = molecular only, then scale G_data by multipliers
    MIX_VALUES = [0.0, 0.5, 1.0, 2.0, 5.0]

    print("\n[4/4] Running crisis simulations (data-derived masses & G)...\n")
    print(f"  Data-derived G = {G_data:.6f}")
    print(f"  Masses: min={masses.min():.3f}, max={masses.max():.3f}, "
          f"ratio={masses.max()/masses.min():.1f}×")
    print()
    print("=" * 95)
    print(f"{'Crisis':20s} | {'λ_G':>6s} | {'eff. G':>8s} | {'mean_cos':>9s} | {'frac≥0.7':>8s} | "
          f"{'‖F_mol‖':>8s} | {'‖F_grav‖':>9s} | {'Φ_total':>10s}")
    print("-" * 95)

    results = {}

    for crisis_name, crisis_date in CRISIS_DATES.items():
        idx = np.argmin(np.abs(dates - pd.Timestamp(crisis_date)))
        X_crisis = X_all[idx]

        results[crisis_name] = {}

        for mix_grav in MIX_VALUES:
            if mix_grav == 0.0:
                dyn = mol_engine.simulate_and_align(
                    X_crisis, mu_eq, bsdt_mol, n_steps=100, eta=0.02)
                F_mol_norm = np.linalg.norm(mol_engine.total_force(X_crisis, mu_eq))
                F_grav_norm = 0.0
                E_total = mol_engine.total_energy(X_crisis, mu_eq)
            else:
                dyn = newton_engine.simulate_and_align(
                    X_crisis, mu_eq, bsdt_new,
                    masses=masses, mix_grav=mix_grav,
                    n_steps=100, eta=0.02, G=G_data)
                F_mol_norm = np.linalg.norm(
                    newton_engine.radial_force(X_crisis, mu_eq) +
                    newton_engine.pairwise_force(X_crisis))
                F_grav_norm = np.linalg.norm(
                    newton_engine.newtonian_force(X_crisis, masses, G=G_data))
                E_total = newton_engine.total_energy(
                    X_crisis, mu_eq, masses=masses, mix_grav=mix_grav, G=G_data)

            label = "mol-only" if mix_grav == 0 else f"{mix_grav:.1f}"
            eff_G = G_data * mix_grav if mix_grav > 0 else 0.0

            results[crisis_name][mix_grav] = {
                **dyn,
                "F_mol_norm": F_mol_norm,
                "F_grav_norm": F_grav_norm * mix_grav,
                "E_total": E_total,
            }

            print(f"{crisis_name:20s} | {label:>6s} | {eff_G:>8.5f} | {dyn['mean_cos']:>+9.4f} | "
                  f"{dyn['frac_above_07']*100:>7.1f}% | "
                  f"{F_mol_norm:>8.2f} | {F_grav_norm*mix_grav:>9.2f} | "
                  f"{E_total:>+10.2f}")

        print("-" * 95)

    return results


def run_trajectory_analysis(X_all, dates, mu_eq, X_normal, masses, G_data):
    """Full trajectory analysis with the Newtonian engine over all quarters."""
    mix_grav = 1.0  # G_data is already calibrated from data
    print("\n" + "=" * 70)
    print(f"  Full trajectory analysis (all quarters, G={G_data:.6f}, λ_G={mix_grav})")
    print("=" * 70)

    bsdt = newton_engine.BSDTOperator().fit(X_normal)

    t0 = time.perf_counter()
    stats = newton_engine.analyse_trajectory(
        X_all, mu_eq, bsdt,
        masses=masses, mix_grav=mix_grav,
        alpha=newton_engine.ALPHA,
        n_power_iter=10,
        verbose=True, G=G_data)
    elapsed = time.perf_counter() - t0

    # Also run molecular-only for comparison
    bsdt_mol = mol_engine.BSDTOperator().fit(X_normal)
    stats_mol = mol_engine.analyse_trajectory(
        X_all, mu_eq, bsdt_mol,
        alpha=mol_engine.ALPHA,
        n_power_iter=10,
        verbose=False)

    print(f"\n  Computed in {elapsed:.1f}s")
    print(f"\n  {'Metric':30s} | {'Molecular':>12s} | {'+ Gravity':>12s} | {'Δ':>10s}")
    print("  " + "-" * 70)

    comparisons = [
        ("Mean energy Φ",        stats_mol["energy"].mean(),     stats["energy"].mean()),
        ("Mean ‖F‖",             stats_mol["force_norm"].mean(), stats["force_norm"].mean()),
        ("Mean MFLS",            stats_mol["mfls"].mean(),       stats["mfls"].mean()),
        ("Mean cos θ",           stats_mol["cos_theta"].mean(),  stats["cos_theta"].mean()),
        ("Mean λ_max",           stats_mol["lambda_max"].mean(), stats["lambda_max"].mean()),
        ("Mean γ*",              stats_mol["gamma_star"].mean(), stats["gamma_star"].mean()),
        ("Frac above critical",  stats_mol["above_cman"].mean(), stats["above_cman"].mean()),
    ]

    for name, v_mol, v_new in comparisons:
        delta = v_new - v_mol
        print(f"  {name:30s} | {v_mol:>+12.4f} | {v_new:>+12.4f} | {delta:>+10.4f}")

    # Gravity-specific diagnostics
    print(f"\n  Gravity diagnostics (λ_G = {mix_grav}):")
    print(f"    Mean Φ_grav          = {stats['grav_energy'].mean():+.4f}")
    print(f"    Mean ‖F_grav‖        = {stats['grav_force_norm'].mean():.4f}")
    print(f"    Φ_grav / Φ_total     = {abs(stats['grav_energy'].mean()) / (abs(stats['energy'].mean()) + 1e-12):.2%}")
    print(f"    ‖F_grav‖ / ‖F_total‖ = {stats['grav_force_norm'].mean() / (stats['force_norm'].mean() + 1e-12):.2%}")

    # Per-crisis comparison
    print(f"\n  Crisis-period breakdown:")
    print(f"  {'Period':20s} | {'Mol cos θ':>10s} | {'New cos θ':>10s} | {'Mol MFLS':>10s} | {'New MFLS':>10s}")
    print("  " + "-" * 70)
    for crisis_name, crisis_date in CRISIS_DATES.items():
        idx = np.argmin(np.abs(dates - pd.Timestamp(crisis_date)))
        # Window: crisis ± 4 quarters
        lo, hi = max(0, idx - 4), min(len(dates), idx + 5)
        cos_mol = stats_mol["cos_theta"][lo:hi].mean()
        cos_new = stats["cos_theta"][lo:hi].mean()
        mfls_mol = stats_mol["mfls"][lo:hi].mean()
        mfls_new = stats["mfls"][lo:hi].mean()
        print(f"  {crisis_name:20s} | {cos_mol:>+10.4f} | {cos_new:>+10.4f} | "
              f"{mfls_mol:>10.2f} | {mfls_new:>10.2f}")

    return stats, stats_mol


def print_mass_comparison(mass_results):
    """Print all three data-derived mass methods side by side."""
    print("\n  Mass comparison (all derived from data, zero heuristics):")
    print(f"  {'Sector':28s} | {'influence':>10s} | {'energy':>10s} | {'variance':>10s}")
    print("  " + "-" * 68)
    for i in range(len(SECTOR_NAMES)):
        print(f"  {SECTOR_NAMES[i]:28s} | "
              f"{mass_results['influence'][i]:>10.3f} | "
              f"{mass_results['energy'][i]:>10.3f} | "
              f"{mass_results['variance'][i]:>10.3f}")
    # Correlation between methods
    from itertools import combinations
    print("\n  Cross-method correlation:")
    for a, b in combinations(mass_results.keys(), 2):
        r = np.corrcoef(mass_results[a], mass_results[b])[0, 1]
        print(f"    Corr({a}, {b}) = {r:+.4f}")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    t_start = time.perf_counter()

    X_all, dates, X_normal, mu_eq = load_fred_data()
    masses, G_data, mass_results = derive_masses_and_G(X_all)
    print_mass_comparison(mass_results)

    results = run_crisis_comparison(X_all, dates, mu_eq, X_normal, masses, G_data)
    stats_new, stats_mol = run_trajectory_analysis(X_all, dates, mu_eq, X_normal, masses, G_data)

    # Summary
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print("  The Newtonian gravity term adds long-range 1/r² attraction")
    print("  weighted by sector systemic importance (mass).")
    print()
    print(f"  Data-derived G = {G_data:.6f}")
    print(f"  Mass method = 'influence' (cross-sector correlation magnitude)")
    print(f"  Key findings:")
    for crisis_name in CRISIS_DATES:
        r_mol = results[crisis_name][0.0]
        r_grav = results[crisis_name][1.0]
        delta_cos = r_grav["mean_cos"] - r_mol["mean_cos"]
        print(f"    {crisis_name}: cos θ change = {delta_cos:+.4f} "
              f"(mol={r_mol['mean_cos']:.4f} → grav={r_grav['mean_cos']:.4f})")

    elapsed = time.perf_counter() - t_start
    print(f"\n  Total elapsed: {elapsed:.1f}s")
    print("  ✓ Newtonian simulation complete")
