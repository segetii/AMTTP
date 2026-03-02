"""Just run Re=6283 adaptive case."""
import numpy as np, json, time, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from solver import NSParams, NavierStokesSolver, extract_timeseries
from numpy.fft import fftn, ifftn

nu = 0.001; N = 32; T = 0.5; dt = 2.5e-4  # shorter T for speed
params = NSParams(N=N, nu_base=nu, dt=dt, T_final=T, theta=1.0,
                  adaptive=True, integrator="semi_implicit",
                  dealiasing=True, diag_interval=100, heavy_interval=500)
solver = NavierStokesSolver(params)
solver.initialize("taylor_green")
total = int(T / dt)
E_bs = 0.0
t0 = time.time()
for step in range(total):
    solver.state.step = step
    solver.state.t = step * dt
    if step % params.diag_interval == 0:
        diag = solver.compute_diagnostics(heavy=(step % params.heavy_interval == 0))
        E_bs = diag.bsdt.E_bs
        solver.state.diagnostics_history.append(diag)
        if step % 500 == 0:
            print(f"  step={step}, t={solver.state.t:.3f}, Ω={diag.enstrophy:.5f}, "
                  f"ν_eff={diag.nu_effective:.5f}")
    solver._step_semi_implicit(E_bs)
elapsed = time.time() - t0
ts = extract_timeseries(solver.state.diagnostics_history)
g = solver.grid

# P/D balance
u = np.real(ifftn(solver.state.u_hat, axes=(1, 2, 3)))
grad_u_hat = np.zeros((3, 3, N, N, N), dtype=complex)
for i in range(3):
    grad_u_hat[i, 0] = 1j * g.KX * solver.state.u_hat[i]
    grad_u_hat[i, 1] = 1j * g.KY * solver.state.u_hat[i]
    grad_u_hat[i, 2] = 1j * g.KZ * solver.state.u_hat[i]
grad_u = np.real(ifftn(grad_u_hat, axes=(2, 3, 4)))
omega = np.array([grad_u[2,1]-grad_u[1,2], grad_u[0,2]-grad_u[2,0], grad_u[1,0]-grad_u[0,1]])
S = 0.5*(grad_u + np.swapaxes(grad_u, 0, 1))
prod = sum(np.mean(omega[i]*S[i,j]*omega[j]) for i in range(3) for j in range(3))
omega_hat = fftn(omega, axes=(1, 2, 3))
palin = sum(np.sum(g.K2*np.abs(omega_hat[i])**2)/N**6 for i in range(3))
nu_eff = float(np.mean(ts['nu_eff'][-3:]))
PD = float(prod / max(nu_eff * palin, 1e-20))

print(f"\n  Re=6283 ADAPTIVE results:")
print(f"  elapsed={elapsed:.0f}s")
print(f"  peak_Ω={float(np.max(ts['enstrophy'])):.5f}")
print(f"  γ*_max={float(np.max(ts['gamma_star'])):.4f}")
print(f"  ν_eff_max={float(np.max(ts['nu_eff'])):.5f}")
print(f"  P/D={PD:.3f}")
print(f"  BKM={float(ts['bkm_integral'][-1]):.4f}")
print(f"  smooth={'YES' if float(np.max(ts['enstrophy'])) < 1e10 else 'NO'}")

# Also run constant for T=0.5 for fair comparison
print(f"\n  Running Re=6283 CONSTANT (T={T})...")
params2 = NSParams(N=N, nu_base=nu, dt=dt, T_final=T, theta=1.0,
                   adaptive=False, integrator="semi_implicit",
                   dealiasing=True, diag_interval=100, heavy_interval=500)
solver2 = NavierStokesSolver(params2)
solver2.initialize("taylor_green")
E_bs2 = 0.0
t0 = time.time()
for step in range(total):
    solver2.state.step = step
    solver2.state.t = step * dt
    if step % params2.diag_interval == 0:
        diag2 = solver2.compute_diagnostics(heavy=(step % params2.heavy_interval == 0))
        E_bs2 = diag2.bsdt.E_bs
        solver2.state.diagnostics_history.append(diag2)
    solver2._step_semi_implicit(E_bs2)
elapsed2 = time.time() - t0
ts2 = extract_timeseries(solver2.state.diagnostics_history)

u2 = np.real(ifftn(solver2.state.u_hat, axes=(1, 2, 3)))
grad_u_hat2 = np.zeros((3, 3, N, N, N), dtype=complex)
for i in range(3):
    grad_u_hat2[i, 0] = 1j * g.KX * solver2.state.u_hat[i]
    grad_u_hat2[i, 1] = 1j * g.KY * solver2.state.u_hat[i]
    grad_u_hat2[i, 2] = 1j * g.KZ * solver2.state.u_hat[i]
grad_u2 = np.real(ifftn(grad_u_hat2, axes=(2, 3, 4)))
omega2 = np.array([grad_u2[2,1]-grad_u2[1,2], grad_u2[0,2]-grad_u2[2,0], grad_u2[1,0]-grad_u2[0,1]])
S2 = 0.5*(grad_u2 + np.swapaxes(grad_u2, 0, 1))
prod2 = sum(np.mean(omega2[i]*S2[i,j]*omega2[j]) for i in range(3) for j in range(3))
omega_hat2 = fftn(omega2, axes=(1, 2, 3))
palin2 = sum(np.sum(g.K2*np.abs(omega_hat2[i])**2)/N**6 for i in range(3))
PD2 = float(prod2 / max(nu * palin2, 1e-20))

print(f"\n  Re=6283 CONSTANT results:")
print(f"  elapsed={elapsed2:.0f}s")
print(f"  peak_Ω={float(np.max(ts2['enstrophy'])):.5f}")
print(f"  P/D={PD2:.3f}")

ratio = float(np.max(ts['enstrophy'])) / max(float(np.max(ts2['enstrophy'])), 1e-20)
print(f"\n  COMPARISON:")
print(f"  Ω_ratio = {ratio:.4f}")
print(f"  P/D_constant = {PD2:.3f}")
print(f"  P/D_adaptive = {PD:.3f}")
print(f"  P/D reduction = {(1-PD/PD2)*100:.1f}%")

json.dump({
    'Re_6283': {
        'Re': 6283, 
        'constant': {'peak_enstrophy': float(np.max(ts2['enstrophy'])), 'PD': PD2},
        'adaptive': {'peak_enstrophy': float(np.max(ts['enstrophy'])), 'PD': PD,
                     'gamma_max': float(np.max(ts['gamma_star'])),
                     'nu_eff_max': float(np.max(ts['nu_eff']))},
        'enstrophy_ratio': ratio,
    }
}, open('re6283_results.json', 'w'), indent=2)
print("\nDone.")
