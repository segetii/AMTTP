# ══════════════════════════════════════════════════════════════════════
# ROAD FORWARD EXPERIMENTS — All 5 remaining items from the appendix
# ══════════════════════════════════════════════════════════════════════
# Paste into your existing Colab session (solver already loaded).
# If solver is NOT loaded, paste nu_critical_experiment.py cells 1-2 first.
#
# Experiments:
#   4. High-Re extended run (Re=6283, N=128, T=20)
#   5. Random-phase IC (N=128, Re≈1257, T=20)
#   6. P/D ratio + cross-correlation (N=128, Re≈1257, T=10)
#   7. Alternative feedback laws for P/D attractor (N=128, T=5)
#
# Estimated runtime: ~60–90 min on T4, ~30–45 min on A100/H100
# ══════════════════════════════════════════════════════════════════════

import numpy as np
import cupy as cp
from cupyx.scipy.fft import fftn as cfftn, ifftn as cifftn
from scipy.stats import linregress
import time as time_module, json, os
import matplotlib.pyplot as plt

# Quick check that solver is loaded
try:
    _ = NSParams
    _ = NavierStokesSolverGPU
    print("✅ Solver classes found in session")
except NameError:
    raise RuntimeError("Solver not loaded! Paste nu_critical_experiment.py cells 1-2 first.")

# ══════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════

def compute_PD_from_state(u_hat, grid, nu_eff):
    """Compute production P and dissipation D from current state.

    P = ∫ ω_i S_ij ω_j dx   (vortex stretching production)
    D = ν_eff ∫ |∇ω|² dx     (viscous dissipation of enstrophy)

    Returns: P, D, enstrophy, alignment_stats
    """
    N = grid.N
    invN6 = 1.0 / N**6
    iK = [grid.iKX, grid.iKY, grid.iKZ]

    # Vorticity in spectral space
    oh = cp.empty((3, N, N, N), dtype=cp.complex128)
    oh[0] = grid.iKY * u_hat[2] - grid.iKZ * u_hat[1]
    oh[1] = grid.iKZ * u_hat[0] - grid.iKX * u_hat[2]
    oh[2] = grid.iKX * u_hat[1] - grid.iKY * u_hat[0]

    # Palinstrophy ||∇ω||² from spectral data (cheap)
    pali = float((cp.sum(grid.K2[cp.newaxis, :] * cp.abs(oh)**2) * invN6).get())
    D = nu_eff * pali

    # Enstrophy
    enstrophy = float((0.5 * cp.sum(cp.abs(oh)**2) * invN6).get())

    # Vorticity in physical space
    omega = cp.real(cifftn(oh, axes=(1, 2, 3)))

    # Production: ω_i S_ij ω_j via physical-space velocity gradients
    # S_ij = (∂u_i/∂x_j + ∂u_j/∂x_i) / 2
    # Use symmetry: only compute upper triangle
    stretching = cp.zeros((N, N, N), dtype=cp.float64)
    for i in range(3):
        for j in range(i, 3):
            dui_dxj = cp.real(cifftn(iK[j] * u_hat[i], axes=(-3, -2, -1)))
            duj_dxi = cp.real(cifftn(iK[i] * u_hat[j], axes=(-3, -2, -1)))
            S_ij = 0.5 * (dui_dxj + duj_dxi)
            contrib = omega[i] * S_ij * omega[j]
            if i == j:
                stretching += contrib
            else:
                stretching += 2.0 * contrib  # symmetry: i,j + j,i
            del dui_dxj, duj_dxi, S_ij, contrib

    vol = (2.0 * np.pi / N) ** 3
    P = float((cp.sum(stretching) * vol).get())

    # Vorticity-strain alignment: |cos(ω, Sω)| for diagnostics
    # Compute Sω in physical space
    omega_mag = cp.sqrt(cp.sum(omega**2, axis=0))
    omega_mag_safe = cp.maximum(omega_mag, 1e-30)
    # We already have stretching = ω_i S_ij ω_j
    # |cos angle| = |ω·Sω| / (|ω| |Sω|) — but we only have ω·Sω/|ω|² = stretching/|ω|²
    # A simpler metric: mean of |stretching| / |ω|⁴ (not exactly cosine but related)
    # Actually just report mean |ω_i S_ij ω_j / |ω|²| where |ω| > threshold
    mask = omega_mag > 0.1 * float(cp.max(omega_mag).get())
    if cp.sum(mask) > 0:
        alignment = float(cp.mean(cp.abs(stretching[mask]) /
                                   (omega_mag_safe[mask]**2)).get())
    else:
        alignment = 0.0

    max_stretching = float(cp.max(cp.abs(stretching)).get())

    del oh, omega, stretching, omega_mag, omega_mag_safe
    cp.get_default_memory_pool().free_all_blocks()

    return P, D, enstrophy, {'alignment': alignment, 'max_stretching': max_stretching}


def random_phase_ic_gpu(grid, k0=4, seed=42):
    """Random-phase IC with energy spectrum E(k) ~ k² exp(-k²/k₀²).
    Normalized to same KE as Taylor-Green (0.125).
    """
    cp.random.seed(seed)
    N = grid.N

    # Random phases for each component
    phase = cp.random.uniform(0, 2 * np.pi, (3, N, N, N))

    # Amplitude from prescribed spectrum
    K_mag_safe = cp.maximum(grid.K_mag, 1e-10)
    amplitude = K_mag_safe * cp.exp(-grid.K2 / (2.0 * k0**2))
    amplitude[0, 0, 0] = 0.0

    u_hat = cp.zeros((3, N, N, N), dtype=cp.complex128)
    for i in range(3):
        u_hat[i] = amplitude * cp.exp(1j * phase[i])

    # Project divergence-free
    u_hat = grid.project_divergence_free(u_hat)

    # Enforce Hermitian symmetry via real-space roundtrip
    u_real = cp.real(cifftn(u_hat, axes=(1, 2, 3)))
    u_hat = cfftn(u_real, axes=(1, 2, 3))

    # Normalize KE to 0.125 (same as Taylor-Green)
    KE = float((0.5 * cp.sum(cp.abs(u_hat)**2) / N**6).get())
    u_hat *= cp.sqrt(0.125 / max(KE, 1e-30))

    return grid.dealias(grid.project_divergence_free(u_hat))


def run_collecting_PD(solver, verbose=True, pd_interval=1):
    """Run solver, collecting P and D at every pd_interval-th diagnostic step."""
    p = solver.params
    total_steps = int(p.T_final / p.dt)
    E_bs_current = 0.0
    pd_data = []
    diag_count = 0

    for step in range(total_steps):
        solver.step = step
        solver.t = step * p.dt

        if step % p.diag_interval == 0:
            diag = solver.compute_diagnostics()
            E_bs_current = diag.bsdt.E_bs
            solver.history.append(diag)

            if diag_count % pd_interval == 0:
                P, D, enst, align = compute_PD_from_state(
                    solver.u_hat, solver.grid, diag.nu_effective)
                pd_data.append({
                    'time': diag.time, 'P': P, 'D': D,
                    'PD_ratio': P / max(D, 1e-30),
                    'enstrophy': enst, 'nu_eff': diag.nu_effective,
                    'omega_inf': diag.omega_inf, 'KE': diag.kinetic_energy,
                    'alignment': align['alignment'],
                    'max_stretching': align['max_stretching'],
                })

            diag_count += 1

            if verbose and step % (p.diag_interval * 200) == 0:
                PD_str = f"P/D={pd_data[-1]['PD_ratio']:.4f}" if pd_data else ""
                print(f"  t={diag.time:.3f}  E={diag.kinetic_energy:.6f}  "
                      f"Ω={diag.enstrophy:.4f}  ||ω||∞={diag.omega_inf:.4f}  {PD_str}")

            if diag.enstrophy > 1e12 or np.isnan(diag.enstrophy):
                print(f"  BLOW-UP at t={diag.time:.4f}")
                break

        solver._step_semi_implicit(E_bs_current)

    return solver.history, pd_data


def cross_correlation(x, y, max_lag=None):
    """Normalized cross-correlation of x and y as function of lag."""
    x = np.array(x) - np.mean(x)
    y = np.array(y) - np.mean(y)
    n = len(x)
    if max_lag is None:
        max_lag = n // 4
    sx = np.std(x)
    sy = np.std(y)
    if sx < 1e-30 or sy < 1e-30:
        return np.zeros(2 * max_lag + 1), np.arange(-max_lag, max_lag + 1)
    lags = np.arange(-max_lag, max_lag + 1)
    cc = np.zeros(len(lags))
    for idx, lag in enumerate(lags):
        if lag >= 0:
            cc[idx] = np.mean(x[:n - lag] * y[lag:]) / (sx * sy)
        else:
            cc[idx] = np.mean(x[-lag:] * y[:n + lag]) / (sx * sy)
    return cc, lags


class CustomAdaptiveViscosity:
    """Adaptive viscosity with switchable feedback law."""
    def __init__(self, nu_base, theta, adaptive=True, law='standard'):
        self.nu_base = nu_base
        self.theta = theta
        self.adaptive = adaptive
        self.law = law

    def gamma_star(self, E_bs):
        if not self.adaptive:
            return 0.0
        t = self.theta
        if self.law == 'standard':
            return E_bs / (E_bs + t)
        elif self.law == 'tanh':
            return float(np.tanh(E_bs / t))
        elif self.law == 'exponential':
            return 1.0 - float(np.exp(-E_bs / t))
        elif self.law == 'linear':
            return float(min(E_bs / t, 1.0))
        return E_bs / (E_bs + t)

    def nu_effective(self, E_bs):
        return self.nu_base * (1.0 + self.gamma_star(E_bs))


print("✅ Helper functions loaded")
print()


# ══════════════════════════════════════════════════════════════════════
# EXPERIMENT 4: HIGH-Re EXTENDED RUN
# Re = 6283 (ν = 0.001), N = 128, T = 20, constant + adaptive
# ══════════════════════════════════════════════════════════════════════

print("=" * 72)
print("EXPERIMENT 4: High-Re extended run (Re ≈ 6283)")
print("=" * 72)

exp4_results = {}
for mode in ['constant', 'adaptive']:
    print(f"\n  ── {mode} mode ──")
    cp.get_default_memory_pool().free_all_blocks()

    params = NSParams(
        N=128, nu_base=0.001, dt=5e-4, T_final=20.0,
        theta=1.0, adaptive=(mode == 'adaptive'),
        integrator='semi_implicit', diag_interval=10,
    )
    solver = NavierStokesSolverGPU(params)
    solver.initialize('taylor_green')

    t0 = time_module.time()
    history, pd_data = run_collecting_PD(solver, verbose=True, pd_interval=5)
    elapsed = time_module.time() - t0

    ts = extract_timeseries(history)
    peak_idx = int(np.argmax(ts['omega_inf']))
    peak_omega = float(ts['omega_inf'][peak_idx])
    peak_t = float(ts['time'][peak_idx])
    final_omega = float(ts['omega_inf'][-1])
    bkm = float(ts['bkm_integral'][-1])

    # P/D at convergence (last 20% of pd_data)
    if len(pd_data) > 10:
        late_pd = [d['PD_ratio'] for d in pd_data[len(pd_data)*4//5:]]
        pd_mean = np.mean(late_pd)
        pd_std = np.std(late_pd)
    else:
        pd_mean = pd_std = 0.0

    peaked = (peak_t < 0.9 * ts['time'][-1]) and (final_omega < 0.8 * peak_omega)

    exp4_results[mode] = {
        'peak_omega': peak_omega, 'peak_t': peak_t,
        'final_omega': final_omega, 'bkm': bkm,
        'elapsed': elapsed, 'peaked_decayed': peaked,
        'PD_mean': pd_mean, 'PD_std': pd_std,
        'pd_data': pd_data, 'ts': ts,
    }

    print(f"\n  Results ({mode}):")
    print(f"    Peak ||ω||∞ = {peak_omega:.4f} at t = {peak_t:.4f}")
    print(f"    Final ||ω||∞ = {final_omega:.4f} (ratio = {final_omega/peak_omega:.3f})")
    print(f"    BKM integral = {bkm:.2f}")
    print(f"    P/D (late) = {pd_mean:.4f} ± {pd_std:.4f}")
    print(f"    Bounded: {'YES ✅' if peaked else 'UNCLEAR ⚠'}")
    print(f"    Time: {elapsed:.1f}s")

    del solver
    cp.get_default_memory_pool().free_all_blocks()

print(f"\n{'=' * 72}")


# ══════════════════════════════════════════════════════════════════════
# EXPERIMENT 5: RANDOM-PHASE INITIAL CONDITIONS
# N = 128, ν = 0.005 (Re ≈ 1257), T = 20, constant + adaptive
# ══════════════════════════════════════════════════════════════════════

print()
print("=" * 72)
print("EXPERIMENT 5: Random-phase IC (Re ≈ 1257)")
print("=" * 72)

exp5_results = {}
for mode in ['constant', 'adaptive']:
    print(f"\n  ── {mode} mode ──")
    cp.get_default_memory_pool().free_all_blocks()

    params = NSParams(
        N=128, nu_base=0.005, dt=5e-4, T_final=20.0,
        theta=1.0, adaptive=(mode == 'adaptive'),
        integrator='semi_implicit', diag_interval=10,
    )
    solver = NavierStokesSolverGPU(params)
    solver.initialize('taylor_green')  # will be overwritten
    solver.u_hat = random_phase_ic_gpu(solver.grid, k0=4, seed=42)
    solver.t = 0.0
    solver.step = 0
    solver.history = []
    solver.bkm_integral = 0.0
    solver.bsdt = BSDTOperatorNS_GPU()

    t0 = time_module.time()
    history, pd_data = run_collecting_PD(solver, verbose=True, pd_interval=5)
    elapsed = time_module.time() - t0

    ts = extract_timeseries(history)
    peak_idx = int(np.argmax(ts['omega_inf']))
    peak_omega = float(ts['omega_inf'][peak_idx])
    peak_t = float(ts['time'][peak_idx])
    final_omega = float(ts['omega_inf'][-1])
    bkm = float(ts['bkm_integral'][-1])
    peaked = (peak_t < 0.9 * ts['time'][-1]) and (final_omega < 0.8 * peak_omega)

    if len(pd_data) > 10:
        late_pd = [d['PD_ratio'] for d in pd_data[len(pd_data)*4//5:]]
        pd_mean, pd_std = np.mean(late_pd), np.std(late_pd)
    else:
        pd_mean = pd_std = 0.0

    exp5_results[mode] = {
        'peak_omega': peak_omega, 'peak_t': peak_t,
        'final_omega': final_omega, 'bkm': bkm,
        'elapsed': elapsed, 'peaked_decayed': peaked,
        'PD_mean': pd_mean, 'PD_std': pd_std,
        'pd_data': pd_data, 'ts': ts,
    }

    print(f"\n  Results ({mode}):")
    print(f"    Peak ||ω||∞ = {peak_omega:.4f} at t = {peak_t:.4f}")
    print(f"    Final ||ω||∞ = {final_omega:.4f} (ratio = {final_omega/peak_omega:.3f})")
    print(f"    BKM integral = {bkm:.2f}")
    print(f"    P/D (late) = {pd_mean:.4f} ± {pd_std:.4f}")
    print(f"    Bounded: {'YES ✅' if peaked else 'UNCLEAR ⚠'}")
    print(f"    Time: {elapsed:.1f}s")

    del solver
    cp.get_default_memory_pool().free_all_blocks()

print(f"\n{'=' * 72}")


# ══════════════════════════════════════════════════════════════════════
# EXPERIMENT 6: P/D RATIO + CROSS-CORRELATION
# N = 128, ν = 0.005 (Re ≈ 1257), T = 10
# Collect P(t) and D(t) at high frequency for cross-correlation
# ══════════════════════════════════════════════════════════════════════

print()
print("=" * 72)
print("EXPERIMENT 6: P/D ratio + production-dissipation cross-correlation")
print("=" * 72)

exp6_results = {}
for mode in ['constant', 'adaptive']:
    print(f"\n  ── {mode} mode (fine diagnostics) ──")
    cp.get_default_memory_pool().free_all_blocks()

    params = NSParams(
        N=128, nu_base=0.005, dt=5e-4, T_final=10.0,
        theta=1.0, adaptive=(mode == 'adaptive'),
        integrator='semi_implicit',
        diag_interval=5,  # every 5 steps = every 0.0025 time units
    )
    solver = NavierStokesSolverGPU(params)
    solver.initialize('taylor_green')

    t0 = time_module.time()
    history, pd_data = run_collecting_PD(solver, verbose=True, pd_interval=1)
    elapsed = time_module.time() - t0

    # Extract P and D time series
    t_pd = np.array([d['time'] for d in pd_data])
    P_arr = np.array([d['P'] for d in pd_data])
    D_arr = np.array([d['D'] for d in pd_data])
    PD_arr = np.array([d['PD_ratio'] for d in pd_data])
    nu_arr = np.array([d['nu_eff'] for d in pd_data])

    # Cross-correlation of P and D
    dt_diag = float(np.median(np.diff(t_pd)))
    max_lag_steps = min(200, len(P_arr) // 4)
    cc, lags = cross_correlation(P_arr, D_arr, max_lag=max_lag_steps)
    lag_times = lags * dt_diag

    # Find peak cross-correlation and its lag
    peak_cc_idx = np.argmax(np.abs(cc))
    peak_cc_lag = lag_times[peak_cc_idx]
    peak_cc_val = cc[peak_cc_idx]

    # Also cross-correlate P with nu_eff (for adaptive only)
    if mode == 'adaptive':
        cc_pnu, _ = cross_correlation(P_arr, nu_arr, max_lag=max_lag_steps)
        peak_pnu_idx = np.argmax(np.abs(cc_pnu))
        peak_pnu_lag = lag_times[peak_pnu_idx]
        peak_pnu_val = cc_pnu[peak_pnu_idx]
    else:
        cc_pnu = np.zeros_like(cc)
        peak_pnu_lag = peak_pnu_val = 0.0

    # P/D statistics in different phases
    # Growth phase (P/D > 1), decay phase (P/D < 1)
    growth_mask = PD_arr > 1.0
    n_growth = np.sum(growth_mask)
    n_decay = np.sum(~growth_mask)

    # Late-time P/D convergence
    late_start = len(PD_arr) * 3 // 4
    pd_late_mean = np.mean(PD_arr[late_start:])
    pd_late_std = np.std(PD_arr[late_start:])

    exp6_results[mode] = {
        'elapsed': elapsed,
        't_pd': t_pd, 'P': P_arr, 'D': D_arr, 'PD': PD_arr,
        'cc_PD': cc, 'cc_Pnu': cc_pnu, 'lag_times': lag_times,
        'peak_cc_lag': peak_cc_lag, 'peak_cc_val': peak_cc_val,
        'peak_pnu_lag': peak_pnu_lag, 'peak_pnu_val': peak_pnu_val,
        'pd_late_mean': pd_late_mean, 'pd_late_std': pd_late_std,
        'n_growth': int(n_growth), 'n_decay': int(n_decay),
    }

    print(f"\n  Results ({mode}):")
    print(f"    {len(pd_data)} P/D samples over T=10")
    print(f"    P/D (late 25%) = {pd_late_mean:.4f} ± {pd_late_std:.4f}")
    print(f"    Growth (P/D>1): {n_growth} steps, Decay (P/D<1): {n_decay} steps")
    print(f"    Cross-corr(P,D): peak = {peak_cc_val:+.4f} at lag = {peak_cc_lag:.4f}")
    if mode == 'adaptive':
        print(f"    Cross-corr(P,ν): peak = {peak_pnu_val:+.4f} at lag = {peak_pnu_lag:.4f}")
    print(f"    Time: {elapsed:.1f}s")

    del solver
    cp.get_default_memory_pool().free_all_blocks()

print(f"\n{'=' * 72}")


# ══════════════════════════════════════════════════════════════════════
# EXPERIMENT 7: ALTERNATIVE FEEDBACK LAWS — P/D ATTRACTOR
# N = 128, ν = 0.005, T = 5.0
# Compare: standard, tanh, exponential, linear clamp
# ══════════════════════════════════════════════════════════════════════

print()
print("=" * 72)
print("EXPERIMENT 7: P/D attractor under alternative feedback laws")
print("=" * 72)

feedback_laws = ['standard', 'tanh', 'exponential', 'linear']
exp7_results = {}

for law in feedback_laws:
    print(f"\n  ── γ* law: {law} ──")
    cp.get_default_memory_pool().free_all_blocks()

    params = NSParams(
        N=128, nu_base=0.005, dt=5e-4, T_final=5.0,
        theta=1.0, adaptive=True,
        integrator='semi_implicit', diag_interval=10,
    )
    solver = NavierStokesSolverGPU(params)
    solver.initialize('taylor_green')

    # Swap in the custom feedback law
    solver.viscosity = CustomAdaptiveViscosity(0.005, 1.0, True, law)

    t0 = time_module.time()
    history, pd_data = run_collecting_PD(solver, verbose=True, pd_interval=1)
    elapsed = time_module.time() - t0

    ts = extract_timeseries(history)
    PD_arr = np.array([d['PD_ratio'] for d in pd_data])
    late_start = len(PD_arr) * 3 // 4
    pd_late = PD_arr[late_start:]

    # Gamma_star statistics
    gamma_arr = np.array([d.gamma_star for d in history])
    gamma_max = float(np.max(gamma_arr))
    nu_eff_arr = np.array([d.nu_effective for d in history])

    exp7_results[law] = {
        'PD_late_mean': float(np.mean(pd_late)),
        'PD_late_std': float(np.std(pd_late)),
        'gamma_max': gamma_max,
        'peak_omega': float(np.max(ts['omega_inf'])),
        'peak_enstrophy': float(np.max(ts['enstrophy'])),
        'elapsed': elapsed,
        'pd_data': pd_data, 'ts': ts,
    }

    print(f"    P/D (late) = {np.mean(pd_late):.4f} ± {np.std(pd_late):.4f}")
    print(f"    γ*_max = {gamma_max:.4f}")
    print(f"    Peak ||ω||∞ = {np.max(ts['omega_inf']):.4f}")
    print(f"    Time: {elapsed:.1f}s")

    del solver
    cp.get_default_memory_pool().free_all_blocks()

print(f"\n{'=' * 72}")


# ══════════════════════════════════════════════════════════════════════
# PUBLICATION FIGURES
# ══════════════════════════════════════════════════════════════════════

fig, axes = plt.subplots(3, 2, figsize=(15, 18))
fig.suptitle('Road Forward Experiments — N=128, Taylor-Green IC', fontsize=14, y=0.98)

# ── Panel A: High-Re vorticity (Exp 4) ──
ax = axes[0, 0]
for mode, ls in [('constant', '-'), ('adaptive', '--')]:
    d = exp4_results[mode]
    ax.plot(d['ts']['time'], d['ts']['omega_inf'], ls, linewidth=1.2, label=f'{mode}')
ax.set_xlabel('t')
ax.set_ylabel(r'$\|\omega\|_\infty$')
ax.set_title(r'(A) Re $\approx$ 6283: Vorticity evolution, T=20')
ax.legend()
ax.grid(True, alpha=0.3)

# ── Panel B: Random IC vorticity (Exp 5) ──
ax = axes[0, 1]
for mode, ls in [('constant', '-'), ('adaptive', '--')]:
    d = exp5_results[mode]
    ax.plot(d['ts']['time'], d['ts']['omega_inf'], ls, linewidth=1.2, label=f'{mode}')
ax.set_xlabel('t')
ax.set_ylabel(r'$\|\omega\|_\infty$')
ax.set_title(r'(B) Random-phase IC, Re $\approx$ 1257: T=20')
ax.legend()
ax.grid(True, alpha=0.3)

# ── Panel C: P/D ratio (Exp 6) ──
ax = axes[1, 0]
for mode, color in [('constant', 'blue'), ('adaptive', 'red')]:
    d = exp6_results[mode]
    # Subsample for clarity
    step = max(1, len(d['t_pd']) // 500)
    ax.plot(d['t_pd'][::step], d['PD'][::step], color=color,
            linewidth=0.8, alpha=0.7, label=f'{mode}')
ax.axhline(0.5, color='black', linewidth=1, linestyle=':', label='P/D = 0.5')
ax.axhline(1.0, color='gray', linewidth=0.5, linestyle='--')
ax.set_xlabel('t')
ax.set_ylabel('P / D')
ax.set_title(r'(C) Production/Dissipation ratio, Re $\approx$ 1257')
ax.set_ylim([-0.5, 3.0])
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

# ── Panel D: Cross-correlation (Exp 6) ──
ax = axes[1, 1]
for mode, color in [('constant', 'blue'), ('adaptive', 'red')]:
    d = exp6_results[mode]
    ax.plot(d['lag_times'], d['cc_PD'], color=color, linewidth=1.5, label=f'Corr(P,D) {mode}')
if 'adaptive' in exp6_results:
    d = exp6_results['adaptive']
    ax.plot(d['lag_times'], d['cc_Pnu'], color='green', linewidth=1.5,
            linestyle='--', label=r'Corr(P,$\nu_{eff}$) adaptive')
ax.axhline(0, color='gray', linewidth=0.5)
ax.axvline(0, color='gray', linewidth=0.5)
ax.set_xlabel(r'Lag $\epsilon$')
ax.set_ylabel('Cross-correlation')
ax.set_title('(D) Production-dissipation cross-correlation')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

# ── Panel E: P/D under different feedback laws (Exp 7) ──
ax = axes[2, 0]
colors = {'standard': 'red', 'tanh': 'blue', 'exponential': 'green', 'linear': 'orange'}
for law in feedback_laws:
    d = exp7_results[law]
    t_arr = np.array([p['time'] for p in d['pd_data']])
    pd_arr = np.array([p['PD_ratio'] for p in d['pd_data']])
    step = max(1, len(t_arr) // 200)
    ax.plot(t_arr[::step], pd_arr[::step], color=colors[law],
            linewidth=1, alpha=0.8, label=f'γ*={law}')
ax.axhline(0.5, color='black', linewidth=1, linestyle=':', label='P/D = 0.5')
ax.set_xlabel('t')
ax.set_ylabel('P / D')
ax.set_title('(E) P/D under alternative feedback laws')
ax.set_ylim([-0.5, 3.0])
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

# ── Panel F: Summary bar chart ──
ax = axes[2, 1]
laws = list(exp7_results.keys())
pd_means = [exp7_results[l]['PD_late_mean'] for l in laws]
pd_stds = [exp7_results[l]['PD_late_std'] for l in laws]
x_pos = range(len(laws))
bars = ax.bar(x_pos, pd_means, yerr=pd_stds, capsize=5,
              color=[colors[l] for l in laws], alpha=0.8)
ax.axhline(0.5, color='black', linewidth=1, linestyle=':')
ax.set_xticks(x_pos)
ax.set_xticklabels([f'γ*={l}' for l in laws], fontsize=9)
ax.set_ylabel('P/D (late-time mean ± std)')
ax.set_title('(F) P/D attractor: universal across feedback laws?')
ax.grid(True, alpha=0.3, axis='y')

plt.tight_layout()
plt.savefig('road_forward_experiments.png', dpi=200)
plt.savefig('road_forward_experiments.pdf')
plt.show()


# ══════════════════════════════════════════════════════════════════════
# COMPREHENSIVE SUMMARY
# ══════════════════════════════════════════════════════════════════════

print()
print("=" * 72)
print("ROAD FORWARD — COMPREHENSIVE RESULTS SUMMARY")
print("=" * 72)

print("\n── EXP 4: HIGH-Re EXTENDED RUN (Re ≈ 6283, N=128, T=20) ──")
for mode in ['constant', 'adaptive']:
    d = exp4_results[mode]
    print(f"  {mode:>10}: peak ω={d['peak_omega']:.2f} at t={d['peak_t']:.2f}, "
          f"BKM={d['bkm']:.1f}, P/D(late)={d['PD_mean']:.4f}±{d['PD_std']:.4f}, "
          f"bounded={'YES' if d['peaked_decayed'] else 'UNCLEAR'}")

print("\n── EXP 5: RANDOM-PHASE IC (Re ≈ 1257, N=128, T=20) ──")
for mode in ['constant', 'adaptive']:
    d = exp5_results[mode]
    print(f"  {mode:>10}: peak ω={d['peak_omega']:.2f} at t={d['peak_t']:.2f}, "
          f"BKM={d['bkm']:.1f}, P/D(late)={d['PD_mean']:.4f}±{d['PD_std']:.4f}, "
          f"bounded={'YES' if d['peaked_decayed'] else 'UNCLEAR'}")

print("\n── EXP 6: P/D CROSS-CORRELATION (Re ≈ 1257, N=128, T=10) ──")
for mode in ['constant', 'adaptive']:
    d = exp6_results[mode]
    print(f"  {mode:>10}: P/D(late)={d['pd_late_mean']:.4f}±{d['pd_late_std']:.4f}, "
          f"CC(P,D) peak={d['peak_cc_val']:+.4f} at lag={d['peak_cc_lag']:.4f}")
if 'adaptive' in exp6_results:
    d = exp6_results['adaptive']
    print(f"  {'':>10}  CC(P,ν) peak={d['peak_pnu_val']:+.4f} at lag={d['peak_pnu_lag']:.4f}")

print("\n── EXP 7: FEEDBACK LAW COMPARISON (Re ≈ 1257, N=128, T=5) ──")
print(f"  {'Law':>14}  {'P/D (late)':>16}  {'γ*_max':>8}  {'Peak ω':>10}")
for law in feedback_laws:
    d = exp7_results[law]
    print(f"  {law:>14}  {d['PD_late_mean']:.4f}±{d['PD_late_std']:.4f}  "
          f"{d['gamma_max']:.4f}  {d['peak_omega']:.4f}")

# Check if P/D → 0.5 is universal
pd_values = [exp7_results[l]['PD_late_mean'] for l in feedback_laws]
pd_spread = max(pd_values) - min(pd_values)
universal = pd_spread < 0.1
print(f"\n  P/D spread across laws: {pd_spread:.4f}")
print(f"  Universal P/D → 0.5: {'YES ✅' if universal else 'NO ❌'}")

print(f"\n{'=' * 72}")
print("KEY CONCLUSIONS:")
print("=" * 72)

# Exp 4 conclusion
e4c = exp4_results['constant']
print(f"\n1. HIGH-Re (Re≈6283): peak ω={e4c['peak_omega']:.2f}, "
      f"BKM={e4c['bkm']:.1f}, "
      f"{'BOUNDED ✅' if e4c['peaked_decayed'] else 'NEEDS MORE TIME ⚠'}")

# Exp 5 conclusion
e5c = exp5_results['constant']
print(f"\n2. RANDOM IC: peak ω={e5c['peak_omega']:.2f}, "
      f"BKM={e5c['bkm']:.1f}, "
      f"{'BOUNDED ✅' if e5c['peaked_decayed'] else 'NEEDS MORE TIME ⚠'}")
print(f"   (Taylor-Green at same Re: peak ω=11.15, BKM=84.58)")

# Exp 6 conclusion
e6a = exp6_results['adaptive']
e6c = exp6_results['constant']
print(f"\n3. CROSS-CORRELATION:")
print(f"   Adaptive: CC(P,D)={e6a['peak_cc_val']:+.4f} at lag={e6a['peak_cc_lag']:.4f}")
print(f"   Constant: CC(P,D)={e6c['peak_cc_val']:+.4f} at lag={e6c['peak_cc_lag']:.4f}")
print(f"   Adaptive CC(P,ν)={e6a['peak_pnu_val']:+.4f} at lag={e6a['peak_pnu_lag']:.4f}")

# Exp 7 conclusion
print(f"\n4. FEEDBACK LAWS: P/D attractor {'UNIVERSAL' if universal else 'LAW-DEPENDENT'}")
for law in feedback_laws:
    d = exp7_results[law]
    print(f"   {law}: P/D = {d['PD_late_mean']:.4f}")

print(f"\n{'=' * 72}")

# Save JSON
save_data = {
    'exp4_high_re': {mode: {k: v for k, v in d.items()
                            if k not in ('pd_data', 'ts')}
                     for mode, d in exp4_results.items()},
    'exp5_random_ic': {mode: {k: v for k, v in d.items()
                              if k not in ('pd_data', 'ts')}
                       for mode, d in exp5_results.items()},
    'exp6_crosscorr': {mode: {
        'pd_late_mean': d['pd_late_mean'], 'pd_late_std': d['pd_late_std'],
        'peak_cc_val': float(d['peak_cc_val']), 'peak_cc_lag': float(d['peak_cc_lag']),
        'peak_pnu_val': float(d['peak_pnu_val']), 'peak_pnu_lag': float(d['peak_pnu_lag']),
        'n_growth': d['n_growth'], 'n_decay': d['n_decay'],
    } for mode, d in exp6_results.items()},
    'exp7_feedback_laws': {law: {k: v for k, v in d.items()
                                 if k not in ('pd_data', 'ts')}
                           for law, d in exp7_results.items()},
}
with open('road_forward_results.json', 'w') as f:
    json.dump(save_data, f, indent=2, default=str)
print("\n✅ Results saved to road_forward_results.json")
print("✅ Figures saved to road_forward_experiments.png/.pdf")
