"""
Consolidated Reynolds Sweep + Multi-IC Experiments (N=64)

Produces publication-quality evidence for the adaptive viscosity paper.
Covers:
  1. Reynolds sweep: Re ∈ {314, 628, 1257, 3142, 6283} at N=64
  2. Multi-IC robustness: Taylor-Green, ABC, Kida, random at Re=3142
  3. Saves all results to consolidated_results.json

Author: Segun Odeyemi
"""
import numpy as np
import json, time, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from solver import NSParams, NavierStokesSolver, extract_timeseries
from numpy.fft import fftn, ifftn


def single_run(nu, N, T, dt, adaptive, ic="taylor_green", theta=1.0):
    """Run a single simulation and return key metrics."""
    params = NSParams(
        N=N, nu_base=nu, dt=dt, T_final=T, theta=theta,
        adaptive=adaptive, integrator="semi_implicit",
        dealiasing=True, diag_interval=20, heavy_interval=200,
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
                print(f"    ** BLOWUP at step {step}, t={solver.state.t:.4f} **")
                break

        solver._step_semi_implicit(E_bs)

    elapsed = time.time() - t0
    h = solver.state.diagnostics_history
    ts = extract_timeseries(h)

    # Sobolev norms
    K2 = solver.grid.K2
    u_pow = np.sum(np.abs(solver.state.u_hat)**2, axis=0) / N**6
    H1 = float(np.sqrt(np.sum((1 + K2) * u_pow)))
    H2 = float(np.sqrt(np.sum((1 + K2)**2 * u_pow)))

    # Production / Dissipation balance
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
    nu_eff_final = float(np.mean(ts['nu_eff'][-5:]))
    dissipation = nu_eff_final * palinstrophy
    PD = float(production / max(dissipation, 1e-20))

    blew_up = float(np.max(ts['enstrophy'])) > 1e10

    return {
        'peak_enstrophy': float(np.max(ts['enstrophy'])),
        'peak_omega_inf': float(np.max(ts['omega_inf'])),
        'final_energy': float(ts['energy'][-1]),
        'energy_decay_pct': float(
            (ts['energy'][0] - ts['energy'][-1]) / max(ts['energy'][0], 1e-20) * 100),
        'bkm_integral': float(ts['bkm_integral'][-1]),
        'H1': H1,
        'H2': H2,
        'nu_eff_min': float(np.min(ts['nu_eff'])),
        'nu_eff_max': float(np.max(ts['nu_eff'])),
        'gamma_max': float(np.max(ts['gamma_star'])),
        'PD_ratio': PD,
        'smooth': not blew_up,
        'elapsed_s': elapsed,
    }


# ============================================================
# Experiment 1: Reynolds Sweep at N=64
# ============================================================

def reynolds_sweep_n64():
    """Reynolds sweep at N=64 with proper CFL-matched time steps."""
    print("=" * 80)
    print("  EXPERIMENT 1: Reynolds Number Sweep (N=64)")
    print("  Adaptive vs Constant Viscosity — Taylor-Green IC")
    print("=" * 80)

    # (nu, N, T, dt, label)
    configs = [
        (0.02,   64, 2.0,  2e-3,  "Re_314"),
        (0.01,   64, 2.0,  1e-3,  "Re_628"),
        (0.005,  64, 1.0,  5e-4,  "Re_1257"),
        (0.002,  64, 0.5,  2e-4,  "Re_3142"),
        (0.001,  64, 0.5,  1e-4,  "Re_6283"),
    ]

    results = {}

    for nu, N, T, dt, label in configs:
        Re = 2 * np.pi / nu
        print(f"\n{'─' * 70}")
        print(f"  {label}: Re = {Re:.0f}  (ν={nu:.1e}, N={N}, T={T}, dt={dt:.1e})")
        print(f"{'─' * 70}")

        # Constant viscosity
        print(f"  [constant ν] ...", end=" ", flush=True)
        rc = single_run(nu, N, T, dt, adaptive=False)
        print(f"done ({rc['elapsed_s']:.0f}s) "
              f"Ω={rc['peak_enstrophy']:.4f} P/D={rc['PD_ratio']:.3f}")

        # Adaptive viscosity
        print(f"  [adaptive ν] ...", end=" ", flush=True)
        ra = single_run(nu, N, T, dt, adaptive=True)
        print(f"done ({ra['elapsed_s']:.0f}s) "
              f"Ω={ra['peak_enstrophy']:.4f} P/D={ra['PD_ratio']:.3f} "
              f"γ*={ra['gamma_max']:.4f}")

        # Ratios
        enstr_ratio = ra['peak_enstrophy'] / max(rc['peak_enstrophy'], 1e-20)
        bkm_ratio = ra['bkm_integral'] / max(rc['bkm_integral'], 1e-20)
        H2_ratio = ra['H2'] / max(rc['H2'], 1e-20)
        PD_ratio_change = ra['PD_ratio'] / max(rc['PD_ratio'], 1e-20)

        results[label] = {
            'Re': float(Re),
            'nu': nu,
            'N': N,
            'T': T,
            'dt': dt,
            'constant': rc,
            'adaptive': ra,
            'enstrophy_ratio': enstr_ratio,
            'bkm_ratio': bkm_ratio,
            'H2_ratio': H2_ratio,
            'PD_ratio_change': PD_ratio_change,
        }

        print(f"  ⇒  Ω_ratio={enstr_ratio:.4f}  BKM_ratio={bkm_ratio:.4f}  "
              f"P/D_ratio_change={PD_ratio_change:.4f}")

    return results


# ============================================================
# Experiment 2: Multi-IC Robustness
# ============================================================

def multi_ic_experiment():
    """Test adaptive benefit across 4 initial conditions at two Re values."""
    print("\n\n" + "=" * 80)
    print("  EXPERIMENT 2: Multi-IC Robustness")
    print("  Four ICs at Re=628 and Re=3142 (N=64)")
    print("=" * 80)

    ics = ["taylor_green", "abc", "kida", "random"]
    # Two Re values: moderate (628) and challenging (3142)
    re_configs = [
        (0.01,  64, 2.0, 1e-3,  "Re_628"),
        (0.002, 64, 0.5, 2e-4,  "Re_3142"),
    ]

    results = {}

    for nu, N, T, dt, re_label in re_configs:
        Re = 2 * np.pi / nu
        results[re_label] = {'Re': float(Re), 'ics': {}}
        print(f"\n{'═' * 70}")
        print(f"  {re_label}: Re = {Re:.0f}")
        print(f"{'═' * 70}")

        for ic in ics:
            print(f"\n  IC: {ic}")

            print(f"    [constant] ...", end=" ", flush=True)
            rc = single_run(nu, N, T, dt, adaptive=False, ic=ic)
            print(f"done ({rc['elapsed_s']:.0f}s) "
                  f"Ω={rc['peak_enstrophy']:.4f} P/D={rc['PD_ratio']:.3f}")

            print(f"    [adaptive] ...", end=" ", flush=True)
            ra = single_run(nu, N, T, dt, adaptive=True, ic=ic)
            print(f"done ({ra['elapsed_s']:.0f}s) "
                  f"Ω={ra['peak_enstrophy']:.4f} P/D={ra['PD_ratio']:.3f}")

            ratio = ra['peak_enstrophy'] / max(rc['peak_enstrophy'], 1e-20)
            pd_change = ra['PD_ratio'] / max(rc['PD_ratio'], 1e-20)

            results[re_label]['ics'][ic] = {
                'constant': rc,
                'adaptive': ra,
                'enstrophy_ratio': ratio,
                'PD_ratio_change': pd_change,
            }
            print(f"    ⇒  Ω_ratio={ratio:.4f}  P/D_change={pd_change:.4f}")

    return results


# ============================================================
# Main — run all experiments and save consolidated results
# ============================================================

def main():
    t_total = time.time()

    # Experiment 1: Reynolds sweep
    sweep_results = reynolds_sweep_n64()

    # Experiment 2: Multi-IC
    ic_results = multi_ic_experiment()

    # Consolidated save
    consolidated = {
        'metadata': {
            'date': time.strftime('%Y-%m-%d %H:%M:%S'),
            'resolution': 'N=64',
            'integrator': 'semi_implicit',
            'domain': 'T^3 = [0,2pi]^3',
            'dealiasing': '2/3 rule',
            'ic_default': 'Taylor-Green',
        },
        'reynolds_sweep': sweep_results,
        'multi_ic': ic_results,
    }

    fname = os.path.join(os.path.dirname(__file__), 'consolidated_results_n64.json')
    with open(fname, 'w') as f:
        json.dump(consolidated, f, indent=2)
    print(f"\n\nResults saved to {fname}")

    # ============================================================
    # Summary tables
    # ============================================================

    print(f"\n\n{'=' * 95}")
    print(f"  SUMMARY TABLE 1 — Reynolds Sweep (N=64)")
    print(f"{'=' * 95}")
    print(f"{'Re':>8} {'Ω_const':>10} {'Ω_adapt':>10} {'Ω_ratio':>9} "
          f"{'P/D_c':>8} {'P/D_a':>8} {'P/D_chg':>8} {'γ*_max':>7} {'Status':>10}")
    print(f"{'─' * 95}")

    for label, r in sweep_results.items():
        c, a = r['constant'], r['adaptive']
        st = "SMOOTH" if c['smooth'] and a['smooth'] else (
            "ADAPT_WIN" if not c['smooth'] and a['smooth'] else
            "BOTH_BLOW" if not c['smooth'] else "SMOOTH")
        print(f"{r['Re']:8.0f} {c['peak_enstrophy']:10.4f} {a['peak_enstrophy']:10.4f} "
              f"{r['enstrophy_ratio']:9.4f} "
              f"{c['PD_ratio']:8.3f} {a['PD_ratio']:8.3f} {r['PD_ratio_change']:8.4f} "
              f"{a['gamma_max']:7.4f} {st:>10}")

    print(f"\nΩ_ratio < 1 ⇒ adaptive reduces enstrophy")
    print(f"P/D_chg < 1 ⇒ adaptive shifts balance toward dissipation")

    # Multi-IC table
    print(f"\n\n{'=' * 85}")
    print(f"  SUMMARY TABLE 2 — Multi-IC Robustness")
    print(f"{'=' * 85}")
    print(f"{'Re':>6} {'IC':>14} {'Ω_c':>10} {'Ω_a':>10} {'Ω_ratio':>9} "
          f"{'P/D_c':>8} {'P/D_a':>8}")
    print(f"{'─' * 85}")

    for re_label, r in ic_results.items():
        for ic, ir in r['ics'].items():
            c, a = ir['constant'], ir['adaptive']
            print(f"{r['Re']:6.0f} {ic:>14} {c['peak_enstrophy']:10.4f} "
                  f"{a['peak_enstrophy']:10.4f} {ir['enstrophy_ratio']:9.4f} "
                  f"{c['PD_ratio']:8.3f} {a['PD_ratio']:8.3f}")

    elapsed_total = time.time() - t_total
    print(f"\n\nTotal experiment time: {elapsed_total/60:.1f} minutes")
    print("Done.")


if __name__ == "__main__":
    main()
