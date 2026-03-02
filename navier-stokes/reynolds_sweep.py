"""
CRITICAL EXPERIMENT: Reynolds Number Sweep
==========================================
Compare adaptive vs constant viscosity across increasing Re.

The key prediction: as Re increases (ν decreases),
the benefit of adaptive viscosity ν(E_BS) should INCREASE.

At low Re:  both are smooth → small difference
At high Re: constant ν may struggle → adaptive provides safety margin
Trend:  enstrophy_ratio = peak_Ω(adaptive) / peak_Ω(constant) should DECREASE with Re

Also tracks:
- Enstrophy production vs dissipation balance
- Vortex stretching suppression
- H^s norm evolution (s = 0, 1, 2)
- BKM integral growth rate
- Depletion ratio evolution

Author: Segun Odeyemi
"""

import numpy as np
import json
import time
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from solver import (NSParams, NavierStokesSolver, extract_timeseries,
                    SpectralGrid, BSDTOperatorNS, AdaptiveViscosity)
from numpy.fft import fftn, ifftn


def compute_sobolev_norms(u_hat, grid):
    """Compute H^s norms for s = 0, 1, 2, 3."""
    K2 = grid.K2
    N = grid.N
    # ||u||²_{H^s} = Σ_k (1 + |k|²)^s |û_k|²  / N^6
    u_power = np.sum(np.abs(u_hat)**2, axis=0) / N**6
    
    H0 = np.sum(u_power)                          # L²
    H1 = np.sum((1 + K2) * u_power)               # H¹
    H2 = np.sum((1 + K2)**2 * u_power)             # H²
    H3 = np.sum((1 + K2)**3 * u_power)             # H³
    
    return {
        'H0': float(np.sqrt(H0)),
        'H1': float(np.sqrt(H1)),
        'H2': float(np.sqrt(H2)),
        'H3': float(np.sqrt(H3)),
    }


def compute_enstrophy_balance(u_hat, grid, nu_eff):
    """
    Compute enstrophy production and dissipation separately.
    
    Enstrophy equation:
        dΩ/dt = ∫ ω·(S·ω) dx  -  ν ∫ |∇ω|² dx
                 [production]       [dissipation]
    
    The ratio P/D is the key indicator:
        P/D < 1 → dissipation dominates → enstrophy decays
        P/D > 1 → production dominates → enstrophy grows
        P/D = 1 → equilibrium
    """
    N = grid.N
    u = np.real(ifftn(u_hat, axes=(1, 2, 3)))
    
    # Velocity gradients
    grad_u_hat = np.zeros((3, 3, N, N, N), dtype=complex)
    for i in range(3):
        grad_u_hat[i, 0] = 1j * grid.KX * u_hat[i]
        grad_u_hat[i, 1] = 1j * grid.KY * u_hat[i]
        grad_u_hat[i, 2] = 1j * grid.KZ * u_hat[i]
    grad_u = np.real(ifftn(grad_u_hat, axes=(2, 3, 4)))
    
    # Vorticity
    omega = np.array([
        grad_u[2, 1] - grad_u[1, 2],
        grad_u[0, 2] - grad_u[2, 0],
        grad_u[1, 0] - grad_u[0, 1]
    ])
    
    # Strain tensor
    S = 0.5 * (grad_u + np.swapaxes(grad_u, 0, 1))
    
    # Production: ∫ ω·(S·ω) dx = Σ_i Σ_j ω_i S_ij ω_j
    production = 0.0
    for i in range(3):
        for j in range(3):
            production += np.mean(omega[i] * S[i, j] * omega[j])
    
    # Dissipation: ν ∫ |∇ω|² dx (palinstrophy)
    # ∇ω in spectral space: i·k_j · ω̂_i
    omega_hat = fftn(omega, axes=(1, 2, 3))
    palinstrophy = 0.0
    for i in range(3):
        palinstrophy += np.sum(grid.K2 * np.abs(omega_hat[i])**2) / N**6
    dissipation = nu_eff * palinstrophy
    
    return {
        'production': float(production),
        'dissipation': float(dissipation),
        'PD_ratio': float(production / max(dissipation, 1e-20)),
        'palinstrophy': float(palinstrophy),
        'net_rate': float(production - dissipation),
    }


def run_single_experiment(nu_base, N, T_final, dt, adaptive, ic_name="taylor_green",
                          theta=1.0, label=""):
    """Run a single NS simulation with extended diagnostics."""
    
    params = NSParams(
        N=N, nu_base=nu_base, dt=dt, T_final=T_final,
        theta=theta, adaptive=adaptive,
        integrator="semi_implicit",
        dealiasing=True,
        diag_interval=10,
        heavy_interval=50,
    )
    
    solver = NavierStokesSolver(params)
    solver.initialize(ic_name)
    
    Re_nominal = 2 * np.pi / nu_base
    print(f"\n{'='*70}")
    print(f"  {label}: Re={Re_nominal:.0f}, N={N}, ν={nu_base:.1e}, "
          f"adaptive={'ON' if adaptive else 'OFF'}")
    print(f"{'='*70}")
    
    # Extended diagnostics storage
    sobolev_history = []
    balance_history = []
    
    total_steps = int(T_final / dt)
    E_bs_current = 0.0
    t_start = time.time()
    
    print(f"{'Step':>6} {'t':>6} {'KE':>9} {'Enstr':>9} {'||ω||∞':>9} "
          f"{'ν_eff':>9} {'γ*':>6} {'P/D':>8} {'H1':>9} {'H2':>9}")
    print("-" * 100)
    
    for step in range(total_steps):
        solver.state.step = step
        solver.state.t = step * dt
        
        do_diag = (step % params.diag_interval == 0)
        do_heavy = (step % params.heavy_interval == 0)
        
        if do_diag:
            diag = solver.compute_diagnostics(heavy=do_heavy)
            E_bs_current = diag.bsdt.E_bs
            solver.state.diagnostics_history.append(diag)
            
            # Extended: Sobolev norms
            snorms = compute_sobolev_norms(solver.state.u_hat, solver.grid)
            sobolev_history.append({
                'time': solver.state.t, 'step': step, **snorms
            })
            
            # Extended: Enstrophy balance (every heavy_interval)
            if do_heavy:
                balance = compute_enstrophy_balance(
                    solver.state.u_hat, solver.grid, diag.nu_effective
                )
                balance_history.append({
                    'time': solver.state.t, 'step': step, **balance
                })
            
            if step % (params.diag_interval * 20) == 0:
                pd_ratio = balance_history[-1]['PD_ratio'] if balance_history else 0
                print(f"{step:6d} {solver.state.t:6.3f} {diag.kinetic_energy:9.5f} "
                      f"{diag.enstrophy:9.5f} {diag.omega_inf:9.4f} "
                      f"{diag.nu_effective:9.6f} {diag.gamma_star:6.3f} "
                      f"{pd_ratio:8.4f} {snorms['H1']:9.4f} {snorms['H2']:9.4f}")
            
            # Blow-up detection
            if diag.enstrophy > 1e10 or np.isnan(diag.enstrophy):
                print(f"\n*** BLOW-UP at t={solver.state.t:.6f}, "
                      f"Ω={diag.enstrophy:.2e} ***")
                break
        
        # Time step
        if params.integrator == "semi_implicit":
            solver._step_semi_implicit(E_bs_current)
        elif params.integrator == "rk4":
            solver._step_rk4(E_bs_current)
        else:
            solver._step_euler(E_bs_current)
    
    elapsed = time.time() - t_start
    print(f"\nCompleted in {elapsed:.1f}s")
    
    # Extract summary
    history = solver.state.diagnostics_history
    ts = extract_timeseries(history)
    
    peak_enstrophy = float(np.max(ts['enstrophy']))
    peak_omega_inf = float(np.max(ts['omega_inf']))
    final_energy = float(ts['energy'][-1])
    energy_decay = float((ts['energy'][0] - ts['energy'][-1]) / ts['energy'][0] * 100)
    bkm = float(ts['bkm_integral'][-1])
    
    # Sobolev norm peaks
    H1_peak = max(s['H1'] for s in sobolev_history)
    H2_peak = max(s['H2'] for s in sobolev_history)
    H3_peak = max(s['H3'] for s in sobolev_history)
    
    # Enstrophy balance summary
    if balance_history:
        mean_PD = np.mean([b['PD_ratio'] for b in balance_history])
        max_PD = max(b['PD_ratio'] for b in balance_history)
        mean_production = np.mean([b['production'] for b in balance_history])
        mean_dissipation = np.mean([b['dissipation'] for b in balance_history])
    else:
        mean_PD = max_PD = mean_production = mean_dissipation = 0
    
    nu_eff_min = float(np.min(ts['nu_eff']))
    nu_eff_max = float(np.max(ts['nu_eff']))
    gamma_max = float(np.max(ts['gamma_star']))
    
    blew_up = peak_enstrophy > 1e10 or np.isnan(peak_enstrophy)
    
    summary = {
        'label': label,
        'Re_nominal': float(Re_nominal),
        'N': N,
        'nu_base': float(nu_base),
        'adaptive': adaptive,
        'T_final': T_final,
        'dt': dt,
        'elapsed_s': elapsed,
        'peak_enstrophy': peak_enstrophy,
        'peak_omega_inf': peak_omega_inf,
        'final_energy': final_energy,
        'energy_decay_pct': energy_decay,
        'bkm_integral': bkm,
        'H1_peak': float(H1_peak),
        'H2_peak': float(H2_peak),
        'H3_peak': float(H3_peak),
        'nu_eff_range': [nu_eff_min, nu_eff_max],
        'gamma_star_max': gamma_max,
        'mean_PD_ratio': float(mean_PD),
        'max_PD_ratio': float(max_PD),
        'mean_production': float(mean_production),
        'mean_dissipation': float(mean_dissipation),
        'smooth': not blew_up,
    }
    
    return summary, history, sobolev_history, balance_history


def reynolds_sweep():
    """
    THE CRITICAL EXPERIMENT: Reynolds number sweep.
    
    For each Re: run constant ν vs adaptive ν(E_BS).
    Track the enstrophy suppression ratio.
    
    Prediction: suppression ratio INCREASES with Re.
    """
    
    # Configuration: push to challenging Reynolds numbers
    # At N=32: can meaningfully resolve Re up to ~400 (DNS) or ~2000 (implicit LES)
    # At N=64: can meaningfully resolve Re up to ~1600 (DNS) or ~8000 (implicit LES)
    
    experiments = [
        # (nu_base, N, T_final, dt, ic_name, label)
        (0.01,   32, 2.0, 1e-3, "taylor_green", "Re_628"),
        (0.005,  32, 2.0, 1e-3, "taylor_green", "Re_1257"),
        (0.002,  32, 2.0, 5e-4, "taylor_green", "Re_3142"),
        (0.001,  32, 2.0, 2.5e-4, "taylor_green", "Re_6283"),
    ]
    
    all_results = {}
    
    for nu, N, T, dt, ic, label_base in experiments:
        Re = 2 * np.pi / nu
        print(f"\n{'#'*70}")
        print(f"  REYNOLDS NUMBER: Re = {Re:.0f}")
        print(f"{'#'*70}")
        
        # Constant viscosity
        label_c = f"{label_base}_constant"
        summary_c, hist_c, sob_c, bal_c = run_single_experiment(
            nu, N, T, dt, adaptive=False, ic_name=ic, label=label_c
        )
        
        # Adaptive viscosity
        label_a = f"{label_base}_adaptive"
        summary_a, hist_a, sob_a, bal_a = run_single_experiment(
            nu, N, T, dt, adaptive=True, ic_name=ic, label=label_a
        )
        
        # Compute comparison metrics
        enstrophy_ratio = summary_a['peak_enstrophy'] / max(summary_c['peak_enstrophy'], 1e-20)
        bkm_ratio = summary_a['bkm_integral'] / max(summary_c['bkm_integral'], 1e-20)
        energy_ratio = summary_a['energy_decay_pct'] / max(summary_c['energy_decay_pct'], 1e-20)
        H1_ratio = summary_a['H1_peak'] / max(summary_c['H1_peak'], 1e-20)
        H2_ratio = summary_a['H2_peak'] / max(summary_c['H2_peak'], 1e-20)
        
        comparison = {
            'Re': float(Re),
            'constant': summary_c,
            'adaptive': summary_a,
            'enstrophy_suppression_ratio': enstrophy_ratio,
            'bkm_ratio': bkm_ratio,
            'energy_decay_ratio': energy_ratio,
            'H1_ratio': H1_ratio,
            'H2_ratio': H2_ratio,
            'both_smooth': summary_c['smooth'] and summary_a['smooth'],
            'adaptive_only_smooth': (not summary_c['smooth']) and summary_a['smooth'],
        }
        
        all_results[label_base] = comparison
        
        print(f"\n{'─'*60}")
        print(f"  Re = {Re:.0f} COMPARISON:")
        print(f"  Peak enstrophy: constant={summary_c['peak_enstrophy']:.4f}, "
              f"adaptive={summary_a['peak_enstrophy']:.4f}, ratio={enstrophy_ratio:.4f}")
        print(f"  BKM integral:   constant={summary_c['bkm_integral']:.4f}, "
              f"adaptive={summary_a['bkm_integral']:.4f}, ratio={bkm_ratio:.4f}")
        print(f"  Energy decay:   constant={summary_c['energy_decay_pct']:.2f}%, "
              f"adaptive={summary_a['energy_decay_pct']:.2f}%")
        print(f"  H1 peak:        constant={summary_c['H1_peak']:.4f}, "
              f"adaptive={summary_a['H1_peak']:.4f}")
        print(f"  H2 peak:        constant={summary_c['H2_peak']:.4f}, "
              f"adaptive={summary_a['H2_peak']:.4f}")
        print(f"  P/D ratio:      constant={summary_c['mean_PD_ratio']:.4f}, "
              f"adaptive={summary_a['mean_PD_ratio']:.4f}")
        print(f"  ν_eff range:    adaptive=[{summary_a['nu_eff_range'][0]:.6f}, "
              f"{summary_a['nu_eff_range'][1]:.6f}]")
        print(f"  γ* max:         {summary_a['gamma_star_max']:.4f}")
        print(f"  Smooth:         constant={'YES' if summary_c['smooth'] else 'BLEW UP'}, "
              f"adaptive={'YES' if summary_a['smooth'] else 'BLEW UP'}")
        print(f"{'─'*60}")
    
    # Save results
    with open('reynolds_sweep_results.json', 'w') as f:
        json.dump(all_results, f, indent=2)
    
    # Print summary table
    print(f"\n{'='*80}")
    print(f"                    REYNOLDS SWEEP SUMMARY TABLE")
    print(f"{'='*80}")
    print(f"{'Re':>8} {'Ω_ratio':>10} {'BKM_ratio':>10} {'H1_ratio':>10} "
          f"{'H2_ratio':>10} {'γ*_max':>8} {'P/D_c':>8} {'P/D_a':>8} {'Status':>12}")
    print(f"{'─'*88}")
    
    for label, comp in all_results.items():
        status = "BOTH_SMOOTH" if comp['both_smooth'] else (
            "ADAPTIVE_WINS" if comp['adaptive_only_smooth'] else "BOTH_BLOWUP"
        )
        print(f"{comp['Re']:8.0f} {comp['enstrophy_suppression_ratio']:10.4f} "
              f"{comp['bkm_ratio']:10.4f} {comp['H1_ratio']:10.4f} "
              f"{comp['H2_ratio']:10.4f} {comp['adaptive']['gamma_star_max']:8.4f} "
              f"{comp['constant']['mean_PD_ratio']:8.4f} "
              f"{comp['adaptive']['mean_PD_ratio']:8.4f} {status:>12}")
    
    print(f"\nKey prediction: Ω_ratio should DECREASE as Re increases")
    print(f"(adaptive ν provides MORE benefit at higher Re)")
    
    return all_results


def multi_ic_experiment():
    """Run all 4 initial conditions at a challenging Re."""
    
    nu = 0.002  # Re ≈ 3142
    N = 32
    T = 2.0
    dt = 5e-4
    theta = 1.0
    
    ics = ["taylor_green", "abc", "kida", "random"]
    all_results = {}
    
    for ic in ics:
        print(f"\n{'#'*70}")
        print(f"  IC: {ic.upper()}, Re ≈ {2*np.pi/nu:.0f}")
        print(f"{'#'*70}")
        
        summary_c, _, _, _ = run_single_experiment(
            nu, N, T, dt, adaptive=False, ic_name=ic, label=f"{ic}_constant"
        )
        summary_a, _, _, _ = run_single_experiment(
            nu, N, T, dt, adaptive=True, ic_name=ic, label=f"{ic}_adaptive"
        )
        
        ratio = summary_a['peak_enstrophy'] / max(summary_c['peak_enstrophy'], 1e-20)
        
        all_results[ic] = {
            'constant': summary_c,
            'adaptive': summary_a,
            'enstrophy_ratio': ratio,
        }
        
        print(f"  {ic}: Ω_ratio = {ratio:.4f}, "
              f"constant_smooth={'Y' if summary_c['smooth'] else 'N'}, "
              f"adaptive_smooth={'Y' if summary_a['smooth'] else 'N'}")
    
    with open('multi_ic_results.json', 'w') as f:
        json.dump(all_results, f, indent=2)
    
    # Summary
    print(f"\n{'='*60}")
    print(f"  MULTI-IC SUMMARY (Re ≈ {2*np.pi/nu:.0f})")
    print(f"{'='*60}")
    print(f"{'IC':>15} {'Ω_const':>10} {'Ω_adapt':>10} {'ratio':>8} {'const':>8} {'adapt':>8}")
    for ic, r in all_results.items():
        print(f"{ic:>15} {r['constant']['peak_enstrophy']:10.4f} "
              f"{r['adaptive']['peak_enstrophy']:10.4f} "
              f"{r['enstrophy_ratio']:8.4f} "
              f"{'SMOOTH' if r['constant']['smooth'] else 'BLOWUP':>8} "
              f"{'SMOOTH' if r['adaptive']['smooth'] else 'BLOWUP':>8}")
    
    return all_results


def theta_sensitivity():
    """Sweep θ parameter to find optimal adaptive damping strength."""
    
    nu = 0.002  # Re ≈ 3142
    N = 32
    T = 1.5
    dt = 5e-4
    
    thetas = [0.01, 0.1, 1.0, 10.0, 100.0]
    
    # Baseline: constant viscosity
    summary_c, _, _, _ = run_single_experiment(
        nu, N, T, dt, adaptive=False, label="constant_baseline"
    )
    
    results = {'constant': summary_c, 'adaptive': {}}
    
    for theta in thetas:
        label = f"theta_{theta}"
        summary_a, _, _, _ = run_single_experiment(
            nu, N, T, dt, adaptive=True, theta=theta, label=label
        )
        ratio = summary_a['peak_enstrophy'] / max(summary_c['peak_enstrophy'], 1e-20)
        results['adaptive'][str(theta)] = {
            'summary': summary_a,
            'enstrophy_ratio': ratio,
        }
        print(f"  θ={theta}: Ω_ratio={ratio:.4f}, γ*_max={summary_a['gamma_star_max']:.4f}")
    
    with open('theta_sensitivity_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n{'='*50}")
    print(f"  θ SENSITIVITY (Re ≈ {2*np.pi/nu:.0f})")
    print(f"{'='*50}")
    print(f"{'θ':>8} {'Ω_ratio':>10} {'γ*_max':>8} {'ν_eff_max':>10}")
    for theta_str, r in results['adaptive'].items():
        s = r['summary']
        print(f"{float(theta_str):8.2f} {r['enstrophy_ratio']:10.4f} "
              f"{s['gamma_star_max']:8.4f} {s['nu_eff_range'][1]:10.6f}")
    
    return results


if __name__ == "__main__":
    print("=" * 80)
    print("  NAVIER-STOKES REGULARITY: REYNOLDS SWEEP")
    print("  Adaptive Viscosity from MFLS Optimal Damping")
    print("=" * 80)
    
    # Run the main experiment
    results = reynolds_sweep()
    
    print("\n\nDone. Results saved to reynolds_sweep_results.json")
