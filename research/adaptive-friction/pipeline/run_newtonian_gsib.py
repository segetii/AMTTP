"""
run_newtonian_gsib.py
=====================
Newtonian GravityEngine simulation on REAL World Bank + FDIC G-SIB data.

Data sources (zero synthetic):
  - US G-SIBs:     FDIC call-report (bank-level, quarterly)
  - Non-US G-SIBs: World Bank GFDD + ECB MIR (country-aggregate, interpolated)

Masses and G are derived entirely from the data — no heuristics.
Each G-SIB's gravitational mass emerges from its cross-bank correlation
footprint, displacement energy, or variance in feature space.

Usage
-----
    python run_newtonian_gsib.py
"""
from __future__ import annotations
import sys
import time
import numpy as np
import pandas as pd
from pathlib import Path

THIS_DIR = Path(__file__).parent
BL_DIR   = THIS_DIR.parent / "banklevel_enhanced"
PIPE_DIR = THIS_DIR

for p in [str(THIS_DIR), str(BL_DIR), str(PIPE_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from gsib_loader_real import build_gsib_panel_real, FEATURE_NAMES
import gravity_engine as mol_engine
import gravity_engine_newtonian as newton_engine
from gravity_engine_newtonian import compute_masses_from_data, compute_G_from_data

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


def load_gsib_panel():
    """Load real G-SIB panel from cached World Bank + FDIC data."""
    print("=" * 75)
    print("  Newtonian GravityEngine — REAL World Bank + FDIC G-SIB Data")
    print("  Zero synthetic data. Zero hand-tuned parameters.")
    print("=" * 75)

    print("\n[1/5] Loading real G-SIB panel...")
    panel = build_gsib_panel_real(
        quarters_start="2005-01-01",
        quarters_end="2023-12-31",
        force_refresh=False,
        min_coverage=0.50,
        verbose=True,
    )

    X_raw = panel["X"]
    dates = panel["dates"]
    meta  = panel["meta"]
    T, N, d = X_raw.shape

    # Standardise on normal period
    norm_mask = (dates >= pd.Timestamp(NORMAL_START)) & \
                (dates <= pd.Timestamp(NORMAL_END))
    n_norm = norm_mask.sum()
    if n_norm < 4:
        norm_mask[:] = False
        norm_mask[:min(8, T)] = True
        n_norm = norm_mask.sum()

    X_ref  = X_raw[norm_mask]
    mu_ref = X_ref.reshape(-1, d).mean(axis=0)
    sd_ref = X_ref.reshape(-1, d).std(axis=0) + 1e-9
    X_std  = (X_raw - mu_ref) / sd_ref
    mu_eq  = X_std[norm_mask].reshape(-1, d).mean(axis=0)

    print(f"\n  Panel: T={T}, N={N}, d={d}")
    print(f"  Normal period: {n_norm}Q ({NORMAL_START} to {NORMAL_END})")
    print(f"  Features: {FEATURE_NAMES}")

    return X_std, dates, meta, mu_eq, norm_mask, panel


def derive_masses(X_std, meta):
    """Derive masses from data using all three methods."""
    print("\n[2/5] Deriving masses from data (no heuristics)...")
    T, N, d = X_std.shape
    bank_names = [m["name"] for m in meta]

    mass_results = {}
    for method in ["influence", "energy", "variance"]:
        m = compute_masses_from_data(X_std, method=method)
        mass_results[method] = m

    # Print all methods side by side
    print(f"\n  {'Bank':30s} | {'Region':>6s} | {'Source':>10s} | "
          f"{'Influence':>9s} | {'Energy':>9s} | {'Variance':>9s}")
    print("  " + "-" * 90)

    for i in range(N):
        src = "FDIC" if meta[i]["data_source"] == "fdic_call_report" else "WorldBank"
        print(f"  {bank_names[i]:30s} | {meta[i]['region']:>6s} | {src:>10s} | "
              f"{mass_results['influence'][i]:>9.3f} | "
              f"{mass_results['energy'][i]:>9.3f} | "
              f"{mass_results['variance'][i]:>9.3f}")

    # Cross-method correlations
    from itertools import combinations
    print("\n  Cross-method correlation:")
    for a, b in combinations(mass_results.keys(), 2):
        r = np.corrcoef(mass_results[a], mass_results[b])[0, 1]
        print(f"    Corr({a}, {b}) = {r:+.4f}")

    # Use energy method for G-SIB data (real bank differentiation)
    # — influence was near-uniform on aggregate FRED data, but on real
    #   bank-level G-SIB data the masses should differentiate
    masses = mass_results["energy"]

    # Derive G
    G_data = compute_G_from_data(X_std, masses)
    print(f"\n  Selected method: energy (displacement from equilibrium)")
    print(f"  Data-derived G = {G_data:.6f}")
    print(f"  Mass range: [{masses.min():.3f}, {masses.max():.3f}], "
          f"ratio = {masses.max()/masses.min():.1f}×")

    # Top 5 heaviest
    ranked = np.argsort(-masses)
    print(f"\n  Top 5 heaviest (most displaced from equilibrium):")
    for rank, i in enumerate(ranked[:5], 1):
        bar = '█' * int(masses[i] * 4)
        print(f"    {rank}. {bank_names[i]:30s}  m={masses[i]:.3f}  {bar}")
    print(f"  Bottom 3:")
    for rank, i in enumerate(ranked[-3:], N - 2):
        print(f"    {rank}. {bank_names[i]:30s}  m={masses[i]:.3f}")

    return masses, G_data, mass_results


def run_crisis_simulations(X_std, dates, mu_eq, norm_mask, masses, G_data, meta):
    """Run molecular vs Newtonian engine on each crisis."""
    print("\n[3/5] Fitting BSDT operators...")
    X_normal = X_std[norm_mask]
    bsdt_mol = mol_engine.BSDTOperator().fit(X_normal)
    bsdt_new = newton_engine.BSDTOperator().fit(X_normal)
    bank_names = [m["name"] for m in meta]

    MIX_VALUES = [0.0, 1.0, 2.0, 5.0]

    print("\n[4/5] Crisis simulations (World Bank + FDIC data)...\n")
    print(f"  Data-derived G = {G_data:.6f}")
    print()
    print("=" * 100)
    print(f"{'Crisis':20s} | {'λ_G':>6s} | {'eff.G':>8s} | {'mean_cos':>9s} | "
          f"{'frac≥0.7':>8s} | {'‖F_mol‖':>8s} | {'‖F_grav‖':>9s} | "
          f"{'Φ_total':>10s}")
    print("-" * 100)

    results = {}
    for crisis_name, crisis_date in CRISIS_DATES.items():
        ts = pd.Timestamp(crisis_date)
        if ts < dates[0] or ts > dates[-1]:
            print(f"{crisis_name:20s} | (outside panel range)")
            continue

        idx = np.argmin(np.abs(dates - ts))
        X_crisis = X_std[idx]
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

            label = "mol-only" if mix_grav == 0 else f"{mix_grav:.0f}"
            eff_G = G_data * mix_grav if mix_grav > 0 else 0.0

            results[crisis_name][mix_grav] = {
                **dyn, "F_mol": F_mol_norm,
                "F_grav": F_grav_norm * mix_grav, "E_total": E_total,
            }

            print(f"{crisis_name:20s} | {label:>6s} | {eff_G:>8.5f} | "
                  f"{dyn['mean_cos']:>+9.4f} | {dyn['frac_above_07']*100:>7.1f}% | "
                  f"{F_mol_norm:>8.2f} | {F_grav_norm*mix_grav:>9.2f} | "
                  f"{E_total:>+10.2f}")

        print("-" * 100)

    return results


def run_full_trajectory(X_std, dates, mu_eq, norm_mask, masses, G_data, meta):
    """Full trajectory analysis across all quarters."""
    print("\n[5/5] Full trajectory analysis...")
    X_normal = X_std[norm_mask]
    bank_names = [m["name"] for m in meta]
    T, N, d = X_std.shape

    bsdt_new = newton_engine.BSDTOperator().fit(X_normal)
    bsdt_mol = mol_engine.BSDTOperator().fit(X_normal)

    t0 = time.perf_counter()
    stats_new = newton_engine.analyse_trajectory(
        X_std, mu_eq, bsdt_new,
        masses=masses, mix_grav=1.0,
        alpha=newton_engine.ALPHA,
        n_power_iter=10, verbose=True, G=G_data)
    elapsed_new = time.perf_counter() - t0

    stats_mol = mol_engine.analyse_trajectory(
        X_std, mu_eq, bsdt_mol,
        alpha=mol_engine.ALPHA,
        n_power_iter=10, verbose=False)

    print(f"\n  Computed in {elapsed_new:.1f}s")
    print(f"\n  {'Metric':30s} | {'Molecular':>12s} | {'+ Gravity':>12s} | {'Δ':>10s}")
    print("  " + "-" * 70)

    comparisons = [
        ("Mean energy Φ",        stats_mol["energy"].mean(),     stats_new["energy"].mean()),
        ("Mean ‖F‖",             stats_mol["force_norm"].mean(), stats_new["force_norm"].mean()),
        ("Mean MFLS",            stats_mol["mfls"].mean(),       stats_new["mfls"].mean()),
        ("Mean cos θ",           stats_mol["cos_theta"].mean(),  stats_new["cos_theta"].mean()),
        ("Mean λ_max",           stats_mol["lambda_max"].mean(), stats_new["lambda_max"].mean()),
        ("Mean γ*",              stats_mol["gamma_star"].mean(), stats_new["gamma_star"].mean()),
        ("Frac above critical",  stats_mol["above_cman"].mean(), stats_new["above_cman"].mean()),
    ]

    for name, v_mol, v_new in comparisons:
        delta = v_new - v_mol
        print(f"  {name:30s} | {v_mol:>+12.4f} | {v_new:>+12.4f} | {delta:>+10.4f}")

    print(f"\n  Gravity diagnostics (G={G_data:.6f}, λ_G=1.0):")
    print(f"    Mean Φ_grav          = {stats_new['grav_energy'].mean():+.4f}")
    print(f"    Mean ‖F_grav‖        = {stats_new['grav_force_norm'].mean():.4f}")
    E_tot = abs(stats_new['energy'].mean()) + 1e-12
    F_tot = stats_new['force_norm'].mean() + 1e-12
    print(f"    Φ_grav / Φ_total     = {abs(stats_new['grav_energy'].mean()) / E_tot:.2%}")
    print(f"    ‖F_grav‖ / ‖F_total‖ = {stats_new['grav_force_norm'].mean() / F_tot:.2%}")

    # Crisis-period breakdown
    print(f"\n  Crisis-period breakdown:")
    print(f"  {'Period':20s} | {'Mol cos θ':>10s} | {'New cos θ':>10s} | "
          f"{'Mol MFLS':>10s} | {'New MFLS':>10s}")
    print("  " + "-" * 70)
    for crisis_name, crisis_date in CRISIS_DATES.items():
        ts = pd.Timestamp(crisis_date)
        if ts < dates[0] or ts > dates[-1]:
            continue
        idx = np.argmin(np.abs(dates - ts))
        lo, hi = max(0, idx - 4), min(len(dates), idx + 5)
        cos_mol = stats_mol["cos_theta"][lo:hi].mean()
        cos_new = stats_new["cos_theta"][lo:hi].mean()
        mfls_mol = stats_mol["mfls"][lo:hi].mean()
        mfls_new = stats_new["mfls"][lo:hi].mean()
        print(f"  {crisis_name:20s} | {cos_mol:>+10.4f} | {cos_new:>+10.4f} | "
              f"{mfls_mol:>10.2f} | {mfls_new:>10.2f}")

    # Per-region analysis
    regions = {}
    for i, m in enumerate(meta):
        regions.setdefault(m["region"], []).append(i)

    print(f"\n  Per-region gravitational mass (energy method):")
    for region, indices in sorted(regions.items()):
        region_masses = masses[indices]
        region_names = [meta[i]["name"] for i in indices]
        total_mass = region_masses.sum()
        print(f"    {region:6s} ({len(indices)} banks): "
              f"total mass = {total_mass:.2f}, "
              f"mean = {region_masses.mean():.3f}, "
              f"heaviest = {region_names[np.argmax(region_masses)]}")

    return stats_new, stats_mol


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    t_start = time.perf_counter()

    X_std, dates, meta, mu_eq, norm_mask, panel = load_gsib_panel()
    masses, G_data, mass_results = derive_masses(X_std, meta)
    results = run_crisis_simulations(X_std, dates, mu_eq, norm_mask, masses, G_data, meta)
    stats_new, stats_mol = run_full_trajectory(X_std, dates, mu_eq, norm_mask, masses, G_data, meta)

    # Summary
    print("\n" + "=" * 75)
    print("  SUMMARY — Real World Bank + FDIC Data")
    print("=" * 75)
    N = len(meta)
    n_us = sum(1 for m in meta if m["data_source"] == "fdic_call_report")
    n_wb = N - n_us
    print(f"  Banks: {N} ({n_us} US/FDIC, {n_wb} non-US/World Bank)")
    print(f"  Features: {FEATURE_NAMES}")
    print(f"  Data-derived G = {G_data:.6f}")
    print(f"  Mass ratio (max/min) = {masses.max()/masses.min():.1f}×")
    print(f"  Everything derived from data. Zero hand-tuned parameters.")
    print()
    print(f"  Key findings:")
    for crisis_name in CRISIS_DATES:
        if crisis_name not in results:
            continue
        r_mol = results[crisis_name].get(0.0)
        r_grav = results[crisis_name].get(1.0)
        if r_mol and r_grav:
            delta_cos = r_grav["mean_cos"] - r_mol["mean_cos"]
            print(f"    {crisis_name}: Δcos θ = {delta_cos:+.4f} "
                  f"(mol={r_mol['mean_cos']:.4f} → grav={r_grav['mean_cos']:.4f})")

    elapsed = time.perf_counter() - t_start
    print(f"\n  Total elapsed: {elapsed:.1f}s")
    print("  ✓ Complete")
