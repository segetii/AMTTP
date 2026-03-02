""" 
Run the core Navier–Stokes numerical experiments used in the paper.

Experiment 1: Constant ν vs Adaptive ν(E) on Taylor-Green vortex
Experiment 2: All 4 initial conditions with adaptive ν
Experiment 3: Vary θ (damping threshold) sensitivity analysis
Experiment 4: Track δ_A (depletion of nonlinearity) before enstrophy spikes

Note: these are finite-resolution numerical experiments on a modified-viscosity
model; they are not a proof of the Clay Millennium problem.
"""

import sys
import os
import json
import numpy as np
import time

sys.path.insert(0, os.path.dirname(__file__))
from solver import (NSParams, NavierStokesSolver, compare_adaptive_vs_constant,
                    extract_timeseries, save_results, INITIAL_CONDITIONS)


def experiment_1_adaptive_vs_constant():
    """
    Main comparison experiment.
    Does adaptive ν(E_BS) reduce extreme-gradient indicators and/or avoid
    numerical instability compared to constant ν at the same base Reynolds number?
    """
    print("\n" + "="*70)
    print("  EXPERIMENT 1: Adaptive ν(E) vs Constant ν")
    print("  Initial condition: Taylor-Green vortex")
    print("  Goal: compare diagnostics under matched base ν₀.")
    print("="*70)

    params = NSParams(
        N=32,              # Start with 32³ (fast), scale to 64³/128³ later
        nu_base=5e-3,      # Re ~ 200 (moderate — enough for vortex dynamics)
        dt=2e-3,           # Stable for semi-implicit at this Re
        T_final=5.0,       # Run to t=5
        theta=1.0,         # Adaptive threshold
        integrator="rk4",
        diag_interval=5,
        heavy_interval=25,
    )

    results = compare_adaptive_vs_constant(params, "taylor_green")
    save_results(results, os.path.join(os.path.dirname(__file__),
                                       "exp1_adaptive_vs_constant.json"))
    return results


def experiment_2_all_initial_conditions():
    """
    Run adaptive ν on all 4 initial conditions.
    Show robustness: the adaptive mechanism works regardless of IC.
    """
    print("\n" + "="*70)
    print("  EXPERIMENT 2: All initial conditions with adaptive ν")
    print("="*70)

    params = NSParams(
        N=32,
        nu_base=5e-3,
        dt=2e-3,
        T_final=5.0,
        theta=1.0,
        adaptive=True,
        integrator="rk4",
        diag_interval=5,
        heavy_interval=25,
    )

    results = {}
    for ic_name in ["taylor_green", "abc", "kida", "random"]:
        print(f"\n--- IC: {ic_name} ---")
        solver = NavierStokesSolver(params)
        solver.initialize(ic_name)
        history = solver.run()
        results[ic_name] = history

    save_results(results, os.path.join(os.path.dirname(__file__),
                                       "exp2_all_ics.json"))
    return results


def experiment_3_theta_sensitivity():
    """
    Vary θ from 0.01 (aggressive damping) to 100 (nearly constant ν).
    Explore θ from 0.01 (aggressive damping) to 100 (nearly constant ν).
    Track how diagnostics and numerical stability change with θ.
    """
    print("\n" + "="*70)
    print("  EXPERIMENT 3: θ sensitivity analysis")
    print("="*70)

    theta_values = [0.01, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 100.0]
    results = {}

    for theta in theta_values:
        print(f"\n--- θ = {theta} ---")
        params = NSParams(
            N=32,
            nu_base=5e-3,
            dt=2e-3,
            T_final=5.0,
            theta=theta,
            adaptive=True,
            integrator="rk4",
            diag_interval=5,
            heavy_interval=25,
        )

        solver = NavierStokesSolver(params)
        solver.initialize("taylor_green")
        history = solver.run()
        results[f"theta_{theta}"] = history

    save_results(results, os.path.join(os.path.dirname(__file__),
                                       "exp3_theta_sensitivity.json"))
    return results


def experiment_4_depletion_tracking():
    """
    Track δ_A (alignment anomaly) before EVERY enstrophy spike.
    This is the "calm before the storm" test in fluid mechanics.

    Hypothesis: δ_A drops (alignment increases) before enstrophy spikes,
    then self-regularises (alignment retreats from e₁ back to e₂).
    If this is true, it's the depletion-of-nonlinearity mechanism made
    quantitative through BSDT.
    """
    print("\n" + "="*70)
    print("  EXPERIMENT 4: Depletion of nonlinearity tracking")
    print("  Tracking δ_A before enstrophy spikes")
    print("="*70)

    # Use lower viscosity to push toward blow-up
    params = NSParams(
        N=32,
        nu_base=2e-3,       # Re ~ 500
        dt=1e-3,
        T_final=3.0,
        theta=1.0,
        adaptive=True,       # Adaptive ON
        integrator="rk4",
        diag_interval=2,     # High frequency diagnostics
        heavy_interval=10,   # Frequent alignment tracking
    )

    solver = NavierStokesSolver(params)
    solver.initialize("kida")  # Kida: intense vortex stretching
    history = solver.run()

    save_results({"depletion": history},
                 os.path.join(os.path.dirname(__file__),
                              "exp4_depletion.json"))

    # Also run WITHOUT adaptive to see difference
    params.adaptive = False
    solver2 = NavierStokesSolver(params)
    solver2.initialize("kida")
    history2 = solver2.run()

    save_results({"constant": history2},
                 os.path.join(os.path.dirname(__file__),
                              "exp4_depletion_constant.json"))

    return history, history2


def analyse_results(results_file: str):
    """Analyse saved results and print summary."""
    with open(results_file) as f:
        data = json.load(f)

    print(f"\n{'='*70}")
    print(f"  Analysis: {results_file}")
    print(f"{'='*70}")

    for label, series in data.items():
        t = np.array(series['time'])
        energy = np.array(series['energy'])
        enstrophy = np.array(series['enstrophy'])
        omega_inf = np.array(series['omega_inf'])
        bkm = np.array(series['bkm_integral'])
        delta_A = np.array(series['delta_A'])
        E_bs = np.array(series['E_bs'])
        nu_eff = np.array(series['nu_eff'])

        print(f"\n--- {label} ---")
        print(f"  Duration:           t ∈ [{t[0]:.3f}, {t[-1]:.3f}]")
        print(f"  Final energy:       {energy[-1]:.6f}")
        print(f"  Peak enstrophy:     {np.max(enstrophy):.6f} at t={t[np.argmax(enstrophy)]:.3f}")
        print(f"  Peak ||ω||∞:        {np.max(omega_inf):.4f} at t={t[np.argmax(omega_inf)]:.3f}")
        print(f"  BKM integral:       {bkm[-1]:.4f}")
        print(f"  Peak E_BS:          {np.max(E_bs):.4f}")
        print(f"  δ_A range:          [{np.min(delta_A):.4f}, {np.max(delta_A):.4f}]")
        print(f"  ν_eff range:        [{np.min(nu_eff):.6f}, {np.max(nu_eff):.6f}]")

        # Check for blow-up
        if np.max(enstrophy) > 1e6:
            blow_idx = np.argmax(enstrophy > 1e6)
            print(f"  *** BLOW-UP at t={t[blow_idx]:.4f} ***")
        else:
            print(f"  Solution remains SMOOTH throughout.")

        # Enstrophy growth rate
        if len(enstrophy) > 10:
            d_enstrophy = np.diff(enstrophy)
            dt_series = np.diff(t)
            growth_rate = d_enstrophy / (dt_series + 1e-15)
            peak_growth = np.max(growth_rate)
            print(f"  Peak enstrophy growth rate: {peak_growth:.2f}")

        # Correlation: δ_A before enstrophy spikes
        if len(delta_A) > 20:
            # Find enstrophy peaks
            from scipy.signal import argrelmax
            try:
                peaks = argrelmax(enstrophy, order=5)[0]
                if len(peaks) > 0:
                    print(f"  Enstrophy peaks found: {len(peaks)}")
                    for p_idx in peaks[:5]:
                        if p_idx > 5:
                            delta_A_before = np.mean(delta_A[p_idx-5:p_idx])
                            print(f"    Peak at t={t[p_idx]:.3f}: δ_A(before)={delta_A_before:.4f}")
            except ImportError:
                pass


if __name__ == "__main__":
    t0 = time.time()

    # Run all experiments
    print("\n" + "#"*70)
    print("#  NAVIER-STOKES BSDT EXPERIMENTS")
    print("#  Framework: Adaptive viscosity from MFLS optimal damping")
    print("#  Goal: Numerical evidence for regularity via depletion")
    print("#"*70)

    exp1 = experiment_1_adaptive_vs_constant()
    exp2 = experiment_2_all_initial_conditions()
    exp3 = experiment_3_theta_sensitivity()
    exp4 = experiment_4_depletion_tracking()

    # Analyse
    base = os.path.dirname(__file__)
    for f in ["exp1_adaptive_vs_constant.json", "exp2_all_ics.json",
              "exp3_theta_sensitivity.json", "exp4_depletion.json"]:
        path = os.path.join(base, f)
        if os.path.exists(path):
            analyse_results(path)

    total = time.time() - t0
    print(f"\n\nTotal time: {total:.1f}s")
    print("All experiments complete.")
