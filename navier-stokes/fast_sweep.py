"""
FAST Reynolds Sweep — Key Metrics Only
Run short simulations to capture the TREND of adaptive benefit vs Re.
"""
import numpy as np
import json, time, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from solver import NSParams, NavierStokesSolver, extract_timeseries
from numpy.fft import fftn, ifftn


def fast_run(nu, N, T, dt, adaptive, ic="taylor_green", theta=1.0):
    """Minimal run — just get peak enstrophy, BKM, H1/H2, P/D balance."""
    params = NSParams(
        N=N, nu_base=nu, dt=dt, T_final=T, theta=theta,
        adaptive=adaptive, integrator="semi_implicit",
        dealiasing=True, diag_interval=20, heavy_interval=100,
    )
    solver = NavierStokesSolver(params)
    solver.initialize(ic)
    
    total = int(T / dt)
    E_bs = 0.0
    t0 = time.time()
    
    for step in range(total):
        solver.state.step = step
        solver.state.t = step * dt
        
        if step % params.diag_interval == 0:
            do_heavy = (step % params.heavy_interval == 0)
            diag = solver.compute_diagnostics(heavy=do_heavy)
            E_bs = diag.bsdt.E_bs
            solver.state.diagnostics_history.append(diag)
            
            if diag.enstrophy > 1e10 or np.isnan(diag.enstrophy):
                break
        
        solver._step_semi_implicit(E_bs)
    
    elapsed = time.time() - t0
    h = solver.state.diagnostics_history
    ts = extract_timeseries(h)
    
    # Compute H^s norms from final state
    K2 = solver.grid.K2
    u_pow = np.sum(np.abs(solver.state.u_hat)**2, axis=0) / N**6
    H1 = float(np.sqrt(np.sum((1 + K2) * u_pow)))
    H2 = float(np.sqrt(np.sum((1 + K2)**2 * u_pow)))
    
    # Compute enstrophy balance at final state
    u = np.real(ifftn(solver.state.u_hat, axes=(1, 2, 3)))
    grad_u_hat = np.zeros((3, 3, N, N, N), dtype=complex)
    for i in range(3):
        grad_u_hat[i, 0] = 1j * solver.grid.KX * solver.state.u_hat[i]
        grad_u_hat[i, 1] = 1j * solver.grid.KY * solver.state.u_hat[i]
        grad_u_hat[i, 2] = 1j * solver.grid.KZ * solver.state.u_hat[i]
    grad_u = np.real(ifftn(grad_u_hat, axes=(2, 3, 4)))
    omega = np.array([
        grad_u[2, 1] - grad_u[1, 2],
        grad_u[0, 2] - grad_u[2, 0],
        grad_u[1, 0] - grad_u[0, 1]
    ])
    S = 0.5 * (grad_u + np.swapaxes(grad_u, 0, 1))
    
    production = sum(
        np.mean(omega[i] * S[i, j] * omega[j])
        for i in range(3) for j in range(3)
    )
    omega_hat = fftn(omega, axes=(1, 2, 3))
    palinstrophy = sum(
        np.sum(K2 * np.abs(omega_hat[i])**2) / N**6
        for i in range(3)
    )
    nu_eff = float(np.mean(ts['nu_eff'][-5:]))
    dissipation = nu_eff * palinstrophy
    PD = float(production / max(dissipation, 1e-20))
    
    blew_up = float(np.max(ts['enstrophy'])) > 1e10
    
    return {
        'peak_enstrophy': float(np.max(ts['enstrophy'])),
        'peak_omega_inf': float(np.max(ts['omega_inf'])),
        'final_energy': float(ts['energy'][-1]),
        'energy_decay_pct': float((ts['energy'][0] - ts['energy'][-1]) / ts['energy'][0] * 100),
        'bkm_integral': float(ts['bkm_integral'][-1]),
        'H1_peak': H1,
        'H2_peak': H2,
        'nu_eff_min': float(np.min(ts['nu_eff'])),
        'nu_eff_max': float(np.max(ts['nu_eff'])),
        'gamma_max': float(np.max(ts['gamma_star'])),
        'PD_ratio': PD,
        'smooth': not blew_up,
        'elapsed': elapsed,
    }


def main():
    print("=" * 70)
    print("  FAST REYNOLDS SWEEP — Adaptive vs Constant Viscosity")
    print("=" * 70)
    
    # 5 Re values: push from safe to extreme
    configs = [
        # (nu,    N,  T,   dt,    label)
        (0.02,   32, 1.0, 2e-3, "Re_314"),
        (0.01,   32, 1.0, 1e-3, "Re_628"),
        (0.005,  32, 1.0, 1e-3, "Re_1257"),
        (0.002,  32, 1.0, 5e-4, "Re_3142"),
        (0.001,  32, 1.0, 2.5e-4, "Re_6283"),
        (0.0005, 32, 0.5, 1e-4, "Re_12566"),
    ]
    
    results = {}
    
    for nu, N, T, dt, label in configs:
        Re = 2 * np.pi / nu
        print(f"\n{'─'*60}")
        print(f"  Re = {Re:.0f}  (ν={nu:.1e}, N={N}, T={T})")
        print(f"{'─'*60}")
        
        # Constant
        print(f"  Running constant ν...", end=" ", flush=True)
        rc = fast_run(nu, N, T, dt, adaptive=False)
        print(f"done ({rc['elapsed']:.0f}s)")
        
        # Adaptive
        print(f"  Running adaptive ν...", end=" ", flush=True)
        ra = fast_run(nu, N, T, dt, adaptive=True)
        print(f"done ({ra['elapsed']:.0f}s)")
        
        # Ratios
        enstr_ratio = ra['peak_enstrophy'] / max(rc['peak_enstrophy'], 1e-20)
        bkm_ratio = ra['bkm_integral'] / max(rc['bkm_integral'], 1e-20)
        H2_ratio = ra['H2_peak'] / max(rc['H2_peak'], 1e-20)
        
        results[label] = {
            'Re': float(Re),
            'constant': rc,
            'adaptive': ra,
            'enstrophy_ratio': enstr_ratio,
            'bkm_ratio': bkm_ratio,
            'H2_ratio': H2_ratio,
        }
        
        print(f"  Ω ratio = {enstr_ratio:.4f} | BKM ratio = {bkm_ratio:.4f} | "
              f"H2 ratio = {H2_ratio:.4f}")
        print(f"  P/D: const={rc['PD_ratio']:.3f}, adapt={ra['PD_ratio']:.3f}")
        print(f"  γ*_max = {ra['gamma_max']:.4f} | ν_eff=[{ra['nu_eff_min']:.5f}, {ra['nu_eff_max']:.5f}]")
        status = "BOTH SMOOTH" if rc['smooth'] and ra['smooth'] else (
            "ADAPTIVE WINS" if not rc['smooth'] and ra['smooth'] else
            "BOTH BLOWUP" if not rc['smooth'] and not ra['smooth'] else "???")
        print(f"  Status: {status}")
    
    # Save
    with open('reynolds_sweep_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    # Summary table
    print(f"\n{'='*90}")
    print(f"  SUMMARY TABLE — Key Evidence for Adaptive Viscosity Regularisation")
    print(f"{'='*90}")
    print(f"{'Re':>8} {'Ω_c':>9} {'Ω_a':>9} {'Ω ratio':>9} {'BKM_r':>8} "
          f"{'H2_r':>8} {'P/D_c':>7} {'P/D_a':>7} {'γ*':>6} {'Status':>14}")
    print(f"{'─'*94}")
    
    for label, r in results.items():
        st = "SMOOTH" if r['constant']['smooth'] and r['adaptive']['smooth'] else (
            "ADAPT_WINS" if not r['constant']['smooth'] and r['adaptive']['smooth'] else
            "BOTH_BLOW" if not r['constant']['smooth'] else "SMOOTH")
        print(f"{r['Re']:8.0f} {r['constant']['peak_enstrophy']:9.4f} "
              f"{r['adaptive']['peak_enstrophy']:9.4f} {r['enstrophy_ratio']:9.4f} "
              f"{r['bkm_ratio']:8.4f} {r['H2_ratio']:8.4f} "
              f"{r['constant']['PD_ratio']:7.3f} {r['adaptive']['PD_ratio']:7.3f} "
              f"{r['adaptive']['gamma_max']:6.4f} {st:>14}")
    
    print(f"\nΩ ratio < 1 → adaptive reduces enstrophy (GOOD)")
    print(f"Prediction: Ω ratio DECREASES as Re increases → adaptive benefit GROWS")
    
    # Multi-IC at challenging Re
    print(f"\n\n{'='*70}")
    print(f"  MULTI-IC EXPERIMENT (Re ≈ 3142)")
    print(f"{'='*70}")
    
    ics = ["taylor_green", "abc", "kida", "random"]
    ic_results = {}
    nu_ic = 0.002
    
    for ic in ics:
        print(f"\n  IC: {ic}")
        rc = fast_run(nu_ic, 32, 1.0, 5e-4, adaptive=False, ic=ic)
        ra = fast_run(nu_ic, 32, 1.0, 5e-4, adaptive=True, ic=ic)
        ratio = ra['peak_enstrophy'] / max(rc['peak_enstrophy'], 1e-20)
        ic_results[ic] = {
            'constant': rc, 'adaptive': ra, 'ratio': ratio,
        }
        print(f"    Ω_c={rc['peak_enstrophy']:.4f}, Ω_a={ra['peak_enstrophy']:.4f}, "
              f"ratio={ratio:.4f}, P/D_c={rc['PD_ratio']:.3f}, P/D_a={ra['PD_ratio']:.3f}")
    
    with open('multi_ic_results.json', 'w') as f:
        json.dump(ic_results, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"  IC SUMMARY (Re ≈ {2*np.pi/nu_ic:.0f})")
    print(f"{'='*60}")
    print(f"{'IC':>15} {'Ω_c':>9} {'Ω_a':>9} {'ratio':>8} {'P/D_c':>7} {'P/D_a':>7}")
    for ic, r in ic_results.items():
        print(f"{ic:>15} {r['constant']['peak_enstrophy']:9.4f} "
              f"{r['adaptive']['peak_enstrophy']:9.4f} {r['ratio']:8.4f} "
              f"{r['constant']['PD_ratio']:7.3f} {r['adaptive']['PD_ratio']:7.3f}")
    
    print("\n\nAll results saved. Ready for paper.")


if __name__ == "__main__":
    main()
