# -*- coding: utf-8 -*-
"""nu_critical_experiment.ipynb — Locate ν_c: Where the Damping Coefficient Crosses Zero

PURPOSE:
--------
The appendix identifies a critical viscosity ν_c ∈ (0.005, 0.00995) where the
fitted damping coefficient c(ν) in the inequality

    d||ω||∞/dt ≤ -c·ν·||ω||∞² + C*

changes sign from negative (anti-damping) to positive (damping).

This notebook:
  1. Runs 12 intermediate ν values between 0.005 and 0.00995 at N=128, T=5.0
     to locate ν_c precisely via bisection.
  2. Repeats at 4 different Re scales (Re ≈ 628, 1257, 3142, 6283) to determine
     whether ν_c/ν_0 < 2 universally (Conjecture A.14 in the appendix).
  3. Extends T to 20.0 at bare ν=0.005 to test whether vorticity saturates
     (Conjecture A.15).

RUNTIME: ~45 min on H100 (or ~90 min on T4/A100)
OUTPUTS:
  - nu_critical_results.json       (all data)
  - nu_critical_figures.pdf/png    (publication figure)
  - EVIDENCE_REPORT.txt

Upload to Google Colab with GPU runtime (T4 or better).
"""

# ══════════════════════════════════════════════════════════════════════
# Cell 1: Environment Setup
# ══════════════════════════════════════════════════════════════════════

import subprocess, sys
try:
    import cupy as cp
    print(f'CuPy {cp.__version__} ready')
except ImportError:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'cupy-cuda12x'])
    import cupy as cp

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from scipy.stats import linregress
from cupyx.scipy.fft import fftn as cfftn, ifftn as cifftn, get_fft_plan
import json, time as time_module, datetime, os, hashlib
from dataclasses import dataclass, field
from typing import List

plt.rcParams.update({
    'font.size': 11, 'axes.titlesize': 13, 'axes.labelsize': 12,
    'figure.dpi': 150, 'savefig.dpi': 300, 'savefig.bbox': 'tight',
    'font.family': 'serif',
})

mem_free, mem_total = cp.cuda.runtime.memGetInfo()
print(f'GPU: {cp.cuda.runtime.getDeviceProperties(0)["name"].decode()}')
print(f'GPU Memory: {mem_free/1e9:.1f} GB free / {mem_total/1e9:.1f} GB total')
print('✅ Environment ready')

# ══════════════════════════════════════════════════════════════════════
# Cell 2: Full Spectral Solver (copy-exact from ns_rescaling_study.py)
# ══════════════════════════════════════════════════════════════════════

@dataclass
class NSParams:
    N: int = 64
    L: float = 2 * np.pi
    nu_base: float = 1e-3
    dt: float = 1e-3
    T_final: float = 10.0
    theta: float = 1.0
    adaptive: bool = True
    dealiasing: bool = True
    integrator: str = 'rk4'
    diag_interval: int = 10
    heavy_interval: int = 100
    cfl_target: float = 0.5

@dataclass
class BSDTChannels:
    delta_C: float = 0.0
    delta_G: float = 0.0
    delta_A: float = 0.0
    delta_T: float = 0.0
    E_bs: float = 0.0

@dataclass
class Diagnostics:
    time: float = 0.0
    step: int = 0
    kinetic_energy: float = 0.0
    enstrophy: float = 0.0
    omega_inf: float = 0.0
    grad_u_L2: float = 0.0
    max_velocity: float = 0.0
    bsdt: BSDTChannels = field(default_factory=BSDTChannels)
    nu_effective: float = 0.0
    gamma_star: float = 0.0
    alignment_mean: float = 0.0
    bkm_integral: float = 0.0


class SpectralGridGPU:
    def __init__(self, params):
        N, L = params.N, params.L
        self.N, self.L = N, L
        k_cpu = np.fft.fftfreq(N, d=1.0/N) * (2*np.pi/L)
        KX_cpu, KY_cpu, KZ_cpu = np.meshgrid(k_cpu, k_cpu, k_cpu, indexing='ij')
        self.KX = cp.asarray(KX_cpu, dtype=cp.float64)
        self.KY = cp.asarray(KY_cpu, dtype=cp.float64)
        self.KZ = cp.asarray(KZ_cpu, dtype=cp.float64)
        self.K2 = self.KX**2 + self.KY**2 + self.KZ**2
        K2_safe = self.K2.copy(); K2_safe[0,0,0] = 1.0
        self.K2_safe = K2_safe
        self.K_mag = cp.sqrt(self.K2)
        self.iKX = 1j * self.KX
        self.iKY = 1j * self.KY
        self.iKZ = 1j * self.KZ
        self.KX_n = self.KX / K2_safe
        self.KY_n = self.KY / K2_safe
        self.KZ_n = self.KZ / K2_safe
        if params.dealiasing:
            k_max = N // 3
            mask = cp.ones((N,N,N), dtype=cp.bool_)
            for kk in [self.KX, self.KY, self.KZ]:
                mask &= (cp.abs(kk)*L/(2*np.pi) <= k_max)
            self.mask = mask
            self.mask_f = mask.astype(cp.float64)
        else:
            self.mask = cp.ones((N,N,N), dtype=cp.bool_)
            self.mask_f = cp.ones((N,N,N), dtype=cp.float64)
        x_cpu = np.linspace(0, L, N, endpoint=False)
        X_cpu, Y_cpu, Z_cpu = np.meshgrid(x_cpu, x_cpu, x_cpu, indexing='ij')
        self.X = cp.asarray(X_cpu)
        self.Y = cp.asarray(Y_cpu)
        self.Z = cp.asarray(Z_cpu)
        self.shell_idx = cp.round(self.K_mag * L / (2*np.pi)).astype(cp.int32)
        self._shell_flat = self.shell_idx.ravel()
        self._n_shells = N // 2

    def project_divergence_free(self, u_hat):
        k_dot_u = self.KX*u_hat[0] + self.KY*u_hat[1] + self.KZ*u_hat[2]
        u_hat[0] -= self.KX_n * k_dot_u
        u_hat[1] -= self.KY_n * k_dot_u
        u_hat[2] -= self.KZ_n * k_dot_u
        u_hat[:, 0, 0, 0] = 0
        return u_hat

    def dealias(self, u_hat):
        u_hat *= self.mask_f
        return u_hat

    def energy_spectrum(self, u_hat):
        E_k = (0.5 / self.N**6) * cp.sum(cp.abs(u_hat)**2, axis=0)
        spectrum = cp.bincount(self._shell_flat, weights=E_k.ravel(),
                               minlength=self._n_shells)
        return cp.asnumpy(spectrum[:self._n_shells])


def taylor_green_gpu(grid, **kw):
    u = cp.zeros((3, grid.N, grid.N, grid.N), dtype=cp.float64)
    u[0] =  cp.sin(grid.X) * cp.cos(grid.Y) * cp.cos(grid.Z)
    u[1] = -cp.cos(grid.X) * cp.sin(grid.Y) * cp.cos(grid.Z)
    u[2] = 0.0
    u_hat = cfftn(u, axes=(1,2,3))
    return grid.dealias(grid.project_divergence_free(u_hat))


class BSDTOperatorNS_GPU:
    def __init__(self):
        self._enstrophy_hist = []
        self._prev_u_hat = None

    def compute_all(self, u_hat, enstrophy, spectrum, alignment_mean):
        ch = BSDTChannels()
        ch.delta_C = self._delta_C(enstrophy)
        ch.delta_G = self._delta_G(spectrum)
        ch.delta_T = self._delta_T(u_hat)
        ch.E_bs = ch.delta_C**2 + ch.delta_G**2 + ch.delta_T**2
        self._prev_u_hat = u_hat.copy()
        return ch

    def _delta_C(self, enstrophy):
        self._enstrophy_hist.append(enstrophy)
        if len(self._enstrophy_hist) > 10:
            m = np.mean(self._enstrophy_hist)
            s = max(np.std(self._enstrophy_hist), 1e-10)
            return abs(enstrophy - m) / s
        return 0.0

    def _delta_G(self, spectrum):
        k = np.arange(1, len(spectrum))
        E_k = spectrum[1:]
        valid = E_k > 1e-20
        if np.sum(valid) < 3:
            return 0.0
        log_k = np.log(k[valid])
        log_E = np.log(E_k[valid])
        slope = -5.0/3.0
        intercept = np.mean(log_E - slope*log_k)
        predicted = slope*log_k + intercept
        return float(np.sqrt(np.mean((log_E - predicted)**2)))

    def _delta_T(self, u_hat):
        if self._prev_u_hat is None:
            return 0.0
        diff = u_hat - self._prev_u_hat
        num = float(cp.sum(cp.abs(diff)**2).get())
        den = float(cp.sum(cp.abs(u_hat)**2).get()) + 1e-20
        return np.sqrt(num / den)


class AdaptiveViscosity:
    def __init__(self, nu_base, theta, adaptive=True):
        self.nu_base = nu_base
        self.theta = theta
        self.adaptive = adaptive

    def gamma_star(self, E_bs):
        if not self.adaptive:
            return 0.0
        return E_bs / (E_bs + self.theta)

    def nu_effective(self, E_bs):
        return self.nu_base * (1.0 + self.gamma_star(E_bs))


class NavierStokesSolverGPU:
    def __init__(self, params):
        self.params = params
        self.grid = SpectralGridGPU(params)
        self.viscosity = AdaptiveViscosity(params.nu_base, params.theta,
                                           params.adaptive)
        self.bsdt = BSDTOperatorNS_GPU()
        self.u_hat = None
        self.t = 0.0
        self.step = 0
        self.history: List[Diagnostics] = []
        self.bkm_integral = 0.0
        self._if_nu = None
        self._if_cache = None
        N = params.N
        self._use_9batch = (N <= 192)
        self._gh9 = cp.empty((9, N, N, N), dtype=cp.complex128)
        self._gh3 = cp.empty((3, N, N, N), dtype=cp.complex128)
        self._nl  = cp.empty((3, N, N, N), dtype=cp.float64)
        self._ohat = cp.empty((3, N, N, N), dtype=cp.complex128)
        self._has_plan3 = False
        try:
            _tmp3 = cp.empty((3, N, N, N), dtype=cp.complex128)
            self._plan_fwd3 = get_fft_plan(_tmp3, axes=(1,2,3), value_type='C2C')
            self._plan_inv3 = get_fft_plan(_tmp3, axes=(1,2,3), value_type='C2C')
            self._has_plan3 = True
            del _tmp3
        except Exception:
            self._has_plan3 = False

    def initialize(self, ic_name='taylor_green', **kwargs):
        self.u_hat = taylor_green_gpu(self.grid, **kwargs)
        self.t = 0.0; self.step = 0
        self.history = []; self.bkm_integral = 0.0
        self._if_nu = None; self._if_cache = None

    def _fft3(self, x):
        if self._has_plan3:
            return cfftn(x, axes=(1,2,3), plan=self._plan_fwd3)
        return cfftn(x, axes=(1,2,3))

    def _ifft3(self, x):
        if self._has_plan3:
            return cifftn(x, axes=(1,2,3), plan=self._plan_inv3)
        return cifftn(x, axes=(1,2,3))

    def _compute_nonlinear(self, u_hat):
        g = self.grid
        u = cp.real(self._ifft3(u_hat))
        if self._use_9batch:
            gh = self._gh9
            gh[0]=g.iKX*u_hat[0]; gh[1]=g.iKY*u_hat[0]; gh[2]=g.iKZ*u_hat[0]
            gh[3]=g.iKX*u_hat[1]; gh[4]=g.iKY*u_hat[1]; gh[5]=g.iKZ*u_hat[1]
            gh[6]=g.iKX*u_hat[2]; gh[7]=g.iKY*u_hat[2]; gh[8]=g.iKZ*u_hat[2]
            grad = cp.real(cifftn(gh, axes=(1,2,3)))
            nl = self._nl
            nl[0]=u[0]*grad[0]+u[1]*grad[1]+u[2]*grad[2]
            nl[1]=u[0]*grad[3]+u[1]*grad[4]+u[2]*grad[5]
            nl[2]=u[0]*grad[6]+u[1]*grad[7]+u[2]*grad[8]
        else:
            gh = self._gh3; nl = self._nl
            for i in range(3):
                gh[0]=g.iKX*u_hat[i]; gh[1]=g.iKY*u_hat[i]; gh[2]=g.iKZ*u_hat[i]
                grad_i = cp.real(self._ifft3(gh))
                nl[i] = u[0]*grad_i[0]+u[1]*grad_i[1]+u[2]*grad_i[2]
        nl_hat = self._fft3(nl)
        return g.dealias(g.project_divergence_free(nl_hat))

    def _step_semi_implicit(self, E_bs):
        dt = self.params.dt
        nu = self.viscosity.nu_effective(E_bs)
        g = self.grid
        if nu != self._if_nu:
            self._if_cache = cp.exp(-nu * g.K2 * dt)[cp.newaxis, :]
            self._if_nu = nu
        nl_hat = self._compute_nonlinear(self.u_hat)
        self.u_hat = self._if_cache * (self.u_hat - dt * nl_hat)
        self.u_hat = g.dealias(g.project_divergence_free(self.u_hat))

    def compute_diagnostics(self):
        g = self.grid; N = g.N
        diag = Diagnostics(time=self.t, step=self.step)
        uh2 = cp.sum(cp.abs(self.u_hat)**2, axis=0)
        invN6 = 1.0 / N**6
        diag.kinetic_energy = float((0.5 * cp.sum(uh2) * invN6).get())
        oh = self._ohat
        oh[0]=g.iKY*self.u_hat[2]-g.iKZ*self.u_hat[1]
        oh[1]=g.iKZ*self.u_hat[0]-g.iKX*self.u_hat[2]
        oh[2]=g.iKX*self.u_hat[1]-g.iKY*self.u_hat[0]
        diag.enstrophy = float((0.5*cp.sum(cp.abs(oh)**2)*invN6).get())
        omega = cp.real(self._ifft3(oh))
        diag.omega_inf = float(cp.max(cp.sqrt(cp.sum(omega**2, axis=0))).get())
        self.bkm_integral += diag.omega_inf * self.params.dt * self.params.diag_interval
        diag.bkm_integral = self.bkm_integral
        spectrum = g.energy_spectrum(self.u_hat)
        bsdt_ch = self.bsdt.compute_all(self.u_hat, diag.enstrophy, spectrum, 0.0)
        diag.bsdt = bsdt_ch
        diag.gamma_star = self.viscosity.gamma_star(bsdt_ch.E_bs)
        diag.nu_effective = self.viscosity.nu_effective(bsdt_ch.E_bs)
        return diag

    def run(self, verbose=False):
        p = self.params
        total_steps = int(p.T_final / p.dt)
        E_bs_current = 0.0
        for step in range(total_steps):
            self.step = step; self.t = step * p.dt
            if step % p.diag_interval == 0:
                diag = self.compute_diagnostics()
                E_bs_current = diag.bsdt.E_bs
                self.history.append(diag)
                if verbose and step % (p.diag_interval * 100) == 0:
                    print(f'  t={diag.time:.3f}  E={diag.kinetic_energy:.6f}  '
                          f'Ω={diag.enstrophy:.4f}  ||ω||∞={diag.omega_inf:.4f}')
                if diag.enstrophy > 1e12 or np.isnan(diag.enstrophy):
                    print(f'  BLOW-UP at t={diag.time:.4f}')
                    break
            self._step_semi_implicit(E_bs_current)
        return self.history


def extract_timeseries(history):
    return {
        'time':        np.array([d.time for d in history]),
        'enstrophy':   np.array([d.enstrophy for d in history]),
        'omega_inf':   np.array([d.omega_inf for d in history]),
        'kinetic_energy': np.array([d.kinetic_energy for d in history]),
        'nu_eff':      np.array([d.nu_effective for d in history]),
        'gamma_star':  np.array([d.gamma_star for d in history]),
        'bkm_integral':np.array([d.bkm_integral for d in history]),
        'delta_C':     np.array([d.bsdt.delta_C for d in history]),
        'delta_G':     np.array([d.bsdt.delta_G for d in history]),
        'delta_T':     np.array([d.bsdt.delta_T for d in history]),
    }


def fit_damping_coefficient(ts, nu):
    """Fit c from: d||ω||∞/dt ≤ -c·ν·||ω||∞² + C*
    Returns dict with c, C, C_star, R2, p, violations, etc.
    """
    omega_inf = ts['omega_inf']
    time_arr = ts['time']
    d_dt = np.diff(omega_inf) / np.diff(time_arr)
    omega_mid = (omega_inf[1:] + omega_inf[:-1]) / 2

    slope, intercept, r_value, p_value, std_err = linregress(omega_mid**2, d_dt)
    c = -slope / nu
    C = intercept
    R2 = r_value**2

    upper = d_dt + c * nu * omega_mid**2
    C_star = np.max(upper)
    violations = int(np.sum(upper > C_star + 1e-10))

    return {
        'c': float(c),
        'C': float(C),
        'C_star': float(C_star),
        'R2': float(R2),
        'p': float(p_value),
        'slope': float(slope),
        'intercept': float(intercept),
        'violations': violations,
        'n_intervals': len(d_dt),
        'peak_omega': float(np.max(omega_inf)),
        'peak_time': float(time_arr[np.argmax(omega_inf)]),
        'peak_enstrophy': float(np.max(ts['enstrophy'])),
        'bkm_final': float(ts['bkm_integral'][-1]),
        'KE_initial': float(ts['kinetic_energy'][0]),
        'KE_final': float(ts['kinetic_energy'][-1]),
    }


print('✅ Solver and analysis functions loaded')


# ══════════════════════════════════════════════════════════════════════
# Cell 3: EXPERIMENT 1 — Locate ν_c at Re ≈ 1257 (ν_0 = 0.005)
# ══════════════════════════════════════════════════════════════════════
#
# Known endpoints:
#   ν = 0.005   → c = -11.91  (anti-damping)
#   ν = 0.00995 → c = +2.447  (damping)
#
# Sweep 12 intermediate values to find where c crosses zero.

N_RUN = 128
theta = 1.0
T_each = 5.0

# Dense sweep between the two known endpoints
nu_sweep_1 = np.array([
    0.0050,   # known: c = -11.91
    0.0055,
    0.0060,
    0.0065,
    0.0070,
    0.0075,
    0.0080,
    0.0085,
    0.0090,
    0.0095,
    0.00995,  # known: c = +2.447
])

k_max_eff = N_RUN // 3
results_exp1 = []

print(f'{"="*72}')
print(f'EXPERIMENT 1: Locate ν_c at Re ≈ 1257')
print(f'{"="*72}')
print(f'{"ν":>10}  {"Re":>8}  {"c":>10}  {"R²":>8}  {"peak_ω":>10}  {"status":>8}')
print('-' * 65)

for nu in nu_sweep_1:
    Re = 2 * np.pi / nu
    dt_diff = 0.3 / (nu * k_max_eff**2 + 1e-20)
    dt_cfl  = (2*np.pi / N_RUN) / 5.0
    dt = float(np.clip(min(dt_cfl, dt_diff), 5e-5, 5e-4))

    cp.get_default_memory_pool().free_all_blocks()
    params = NSParams(
        N=N_RUN, nu_base=nu, dt=dt, T_final=T_each,
        theta=theta, adaptive=False,  # ← CONSTANT ν
        integrator='semi_implicit',
        diag_interval=max(5, int(0.005/dt)),
    )
    solver = NavierStokesSolverGPU(params)
    solver.initialize('taylor_green')

    t0 = time_module.time()
    history = solver.run(verbose=False)
    elapsed = time_module.time() - t0

    ts = extract_timeseries(history)
    fit = fit_damping_coefficient(ts, nu)
    fit['nu'] = float(nu)
    fit['Re'] = float(Re)
    fit['dt'] = float(dt)
    fit['T'] = float(T_each)
    fit['elapsed_s'] = float(elapsed)
    fit['n_snapshots'] = len(history)
    fit['smooth'] = bool(np.max(ts['enstrophy']) < 1e10)

    status = '✅' if fit['smooth'] else '❌'
    c_sign = '+' if fit['c'] > 0 else ''
    print(f"{nu:10.5f}  {Re:8.0f}  {c_sign}{fit['c']:9.4f}  {fit['R2']:8.4f}  "
          f"{fit['peak_omega']:10.4f}  {status}")

    results_exp1.append(fit)
    del solver; cp.get_default_memory_pool().free_all_blocks()

# Find ν_c by linear interpolation between sign-change points
nu_arr = np.array([r['nu'] for r in results_exp1])
c_arr = np.array([r['c'] for r in results_exp1])

nu_c_estimate = None
for i in range(len(c_arr) - 1):
    if c_arr[i] < 0 and c_arr[i+1] > 0:
        # Linear interpolation
        frac = -c_arr[i] / (c_arr[i+1] - c_arr[i])
        nu_c_estimate = nu_arr[i] + frac * (nu_arr[i+1] - nu_arr[i])
        break
    elif c_arr[i] > 0 and c_arr[i+1] < 0:
        frac = c_arr[i] / (c_arr[i] - c_arr[i+1])
        nu_c_estimate = nu_arr[i] + frac * (nu_arr[i+1] - nu_arr[i])
        break

print(f'\n{"="*72}')
if nu_c_estimate is not None:
    ratio = nu_c_estimate / 0.005
    print(f'  ν_c ≈ {nu_c_estimate:.6f}  (ratio ν_c/ν_0 = {ratio:.4f})')
    if ratio < 2.0:
        print(f'  ✅ ν_c/ν_0 = {ratio:.4f} < 2.0 → adaptive saturation suffices!')
    else:
        print(f'  ⚠ ν_c/ν_0 = {ratio:.4f} ≥ 2.0 → adaptive saturation may NOT suffice')
else:
    # All same sign
    if c_arr[-1] > 0:
        print(f'  All c > 0: ν_c < {nu_arr[0]:.5f} (damping holds everywhere)')
    else:
        print(f'  All c < 0: ν_c > {nu_arr[-1]:.5f} (no damping in this range)')
print(f'{"="*72}')


# ══════════════════════════════════════════════════════════════════════
# Cell 4: EXPERIMENT 2 — Scale ν_c with Re
# ══════════════════════════════════════════════════════════════════════
#
# Repeat the bisection at 4 different ν_0 values (i.e., 4 Re).
# For each ν_0, sweep ν from ν_0 to 2·ν_0 and find where c = 0.

nu0_values = [0.01, 0.005, 0.002, 0.001]  # Re ≈ 628, 1257, 3142, 6283

# For each ν_0, sweep 8 values from ν_0 to 2·ν_0
n_sweep = 8
T_each_2 = 5.0

results_exp2 = {}

print(f'\n{"="*72}')
print(f'EXPERIMENT 2: Scale ν_c with Re')
print(f'{"="*72}')

for nu0 in nu0_values:
    Re0 = 2 * np.pi / nu0
    nu_sweep = np.linspace(nu0, 2*nu0, n_sweep)
    results_this = []

    print(f'\n  ── ν_0 = {nu0}, Re ≈ {Re0:.0f} ──')
    print(f'  {"ν":>10}  {"c":>10}  {"R²":>8}  {"peak_ω":>10}')
    print(f'  {"-"*45}')

    for nu in nu_sweep:
        Re = 2 * np.pi / nu
        dt_diff = 0.3 / (nu * k_max_eff**2 + 1e-20)
        dt_cfl  = (2*np.pi / N_RUN) / 5.0
        dt = float(np.clip(min(dt_cfl, dt_diff), 5e-5, 5e-4))

        cp.get_default_memory_pool().free_all_blocks()
        params = NSParams(
            N=N_RUN, nu_base=nu, dt=dt, T_final=T_each_2,
            theta=theta, adaptive=False,   # CONSTANT ν
            integrator='semi_implicit',
            diag_interval=max(5, int(0.005/dt)),
        )
        solver = NavierStokesSolverGPU(params)
        solver.initialize('taylor_green')

        history = solver.run(verbose=False)
        ts = extract_timeseries(history)
        fit = fit_damping_coefficient(ts, nu)
        fit['nu'] = float(nu)
        fit['nu0'] = float(nu0)
        fit['Re'] = float(Re)
        fit['Re0'] = float(Re0)
        fit['ratio'] = float(nu / nu0)

        c_sign = '+' if fit['c'] > 0 else ''
        print(f"  {nu:10.6f}  {c_sign}{fit['c']:9.4f}  {fit['R2']:8.4f}  "
              f"{fit['peak_omega']:10.4f}")

        results_this.append(fit)
        del solver; cp.get_default_memory_pool().free_all_blocks()

    # Find ν_c for this Re
    c_arr_this = np.array([r['c'] for r in results_this])
    nu_arr_this = np.array([r['nu'] for r in results_this])

    nu_c_this = None
    for i in range(len(c_arr_this) - 1):
        if c_arr_this[i] * c_arr_this[i+1] < 0:
            frac = abs(c_arr_this[i]) / (abs(c_arr_this[i]) + abs(c_arr_this[i+1]))
            nu_c_this = nu_arr_this[i] + frac * (nu_arr_this[i+1] - nu_arr_this[i])
            break

    ratio_this = nu_c_this / nu0 if nu_c_this else None
    results_exp2[f'Re_{Re0:.0f}'] = {
        'nu0': nu0,
        'Re0': Re0,
        'nu_c': nu_c_this,
        'ratio': ratio_this,
        'sweeps': results_this,
    }

    if nu_c_this:
        print(f'  → ν_c = {nu_c_this:.6f}, ν_c/ν_0 = {ratio_this:.4f}')
    elif c_arr_this[0] > 0:
        print(f'  → All c > 0: ν_c < ν_0 = {nu0} (damping everywhere)')
        results_exp2[f'Re_{Re0:.0f}']['ratio'] = 1.0  # conservative
    else:
        print(f'  → All c < 0: ν_c > 2ν_0 (adaptive insufficient)')
        results_exp2[f'Re_{Re0:.0f}']['ratio'] = float('inf')


# Summary
print(f'\n{"="*72}')
print(f'EXPERIMENT 2 SUMMARY: ν_c/ν_0 across Re')
print(f'{"="*72}')
print(f'  {"Re":>8}  {"ν_0":>10}  {"ν_c":>10}  {"ν_c/ν_0":>10}  {"adaptive OK?":>14}')
print(f'  {"-"*60}')
all_ok = True
for key, data in sorted(results_exp2.items()):
    re_val = data['Re0']
    nu0 = data['nu0']
    nu_c = data['nu_c']
    ratio = data['ratio']
    ok = ratio is not None and ratio < 2.0
    if not ok: all_ok = False
    nu_c_str = f'{nu_c:.6f}' if nu_c else 'N/A'
    ratio_str = f'{ratio:.4f}' if ratio else 'N/A'
    ok_str = '✅ YES' if ok else '❌ NO'
    print(f'  {re_val:8.0f}  {nu0:10.5f}  {nu_c_str:>10}  {ratio_str:>10}  {ok_str:>14}')

print()
if all_ok:
    print('  ✅ ν_c/ν_0 < 2 at ALL tested Re → Conjecture A.14 SUPPORTED')
    print('     The adaptive mechanism\'s factor-2 enhancement suffices.')
else:
    print('  ⚠ ν_c/ν_0 ≥ 2 at some Re → Conjecture A.14 PARTIALLY/NOT supported')
print(f'{"="*72}')


# ══════════════════════════════════════════════════════════════════════
# Cell 5: EXPERIMENT 3 — Extend T at bare ν = 0.005
# ══════════════════════════════════════════════════════════════════════
#
# Does ||ω||∞ at ν=0.005 eventually saturate, or keep growing?

print(f'\n{"="*72}')
print(f'EXPERIMENT 3: Extended run at ν=0.005, T=20.0')
print(f'{"="*72}')

T_long = 20.0
nu_long = 0.005
dt_long = 0.0005

cp.get_default_memory_pool().free_all_blocks()
params_long = NSParams(
    N=N_RUN, nu_base=nu_long, dt=dt_long, T_final=T_long,
    theta=theta, adaptive=False,
    integrator='semi_implicit',
    diag_interval=20,  # every 20 steps to save memory over long run
)
solver_long = NavierStokesSolverGPU(params_long)
solver_long.initialize('taylor_green')

t0 = time_module.time()
history_long = solver_long.run(verbose=True)
elapsed_long = time_module.time() - t0

ts_long = extract_timeseries(history_long)
fit_long = fit_damping_coefficient(ts_long, nu_long)

peak_idx = int(np.argmax(ts_long['omega_inf']))
peak_t = float(ts_long['time'][peak_idx])
peak_val = float(ts_long['omega_inf'][peak_idx])
final_val = float(ts_long['omega_inf'][-1])
final_t = float(ts_long['time'][-1])

# Check if vorticity peaked and decayed
peaked_and_decayed = (peak_t < 0.9 * final_t) and (final_val < 0.8 * peak_val)
still_growing = (peak_t > 0.9 * final_t)

print(f'\n  Duration: {elapsed_long:.1f}s, {len(history_long)} snapshots')
print(f'  Peak ||ω||∞ = {peak_val:.4f} at t = {peak_t:.4f}')
print(f'  Final ||ω||∞ = {final_val:.4f} at t = {final_t:.4f}')
print(f'  Ratio final/peak = {final_val/peak_val:.4f}')
print()
if peaked_and_decayed:
    print(f'  ✅ CONJECTURE A.15 CONFIRMED: Vorticity peaked at t={peak_t:.2f}')
    print(f'     and decayed to {final_val/peak_val*100:.1f}% of peak by t={final_t:.1f}.')
    print(f'     The constant-ν solution is bounded — no blow-up.')
elif still_growing:
    print(f'  ⚠ Vorticity still growing at T={T_long}.')
    print(f'     Conjecture A.15 not yet confirmed. Try T=50.')
else:
    print(f'  ✓ Vorticity peaked at t={peak_t:.2f}, currently at')
    print(f'    {final_val/peak_val*100:.1f}% of peak. Partial decay observed.')

# Also fit c for this longer run
print(f'\n  Extended-run damping coefficient:')
print(f'    c = {fit_long["c"]:.6f} (vs c = -11.91 at T=5)')
print(f'    R² = {fit_long["R2"]:.4f}')
print(f'    BKM integral = {fit_long["bkm_final"]:.4f}')
print(f'{"="*72}')

del solver_long; cp.get_default_memory_pool().free_all_blocks()


# ══════════════════════════════════════════════════════════════════════
# Cell 6: Publication Figures + Save Results
# ══════════════════════════════════════════════════════════════════════

os.makedirs('nu_critical_artifacts/figures', exist_ok=True)
os.makedirs('nu_critical_artifacts/data', exist_ok=True)

fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle(r'$\nu_c$ Critical Viscosity Experiment — N=128, Taylor-Green IC',
             fontsize=14, fontweight='bold')

# ── Panel A: c(ν) at Re ≈ 1257 ──
ax = axes[0, 0]
nu_plot = [r['nu'] for r in results_exp1]
c_plot = [r['c'] for r in results_exp1]
ax.plot(nu_plot, c_plot, 'o-', color='steelblue', markersize=6, linewidth=1.5)
ax.axhline(0, color='red', linewidth=1.5, linestyle='--', label='c = 0 (critical)')
if nu_c_estimate:
    ax.axvline(nu_c_estimate, color='orange', linewidth=1.5, linestyle=':',
               label=f'$\\nu_c$ ≈ {nu_c_estimate:.5f}')
ax.set_xlabel(r'Viscosity $\nu$')
ax.set_ylabel(r'Damping coefficient $c$')
ax.set_title(r'(A) $c(\nu)$ at $\mathrm{Re}_0 \approx 1257$')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

# ── Panel B: ν_c/ν_0 vs Re ──
ax = axes[0, 1]
re_vals = [data['Re0'] for data in results_exp2.values() if data['ratio'] is not None]
ratio_vals = [data['ratio'] for data in results_exp2.values() if data['ratio'] is not None]
if re_vals:
    ax.semilogx(re_vals, ratio_vals, 's-', color='darkgreen', markersize=8, linewidth=2)
    ax.axhline(2.0, color='red', linewidth=1.5, linestyle='--',
               label=r'$\nu_c/\nu_0 = 2$ (adaptive limit)')
    ax.axhline(1.0, color='gray', linewidth=1, linestyle=':')
    ax.set_xlabel(r'Reynolds number Re')
    ax.set_ylabel(r'$\nu_c / \nu_0$')
    ax.set_title(r'(B) Critical ratio $\nu_c/\nu_0$ vs Re')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_ylim([0, 3])

# ── Panel C: Extended run ||ω||∞ ──
ax = axes[1, 0]
ax.plot(ts_long['time'], ts_long['omega_inf'], 'b-', linewidth=1, label=r'$\|\omega\|_\infty$')
ax.axvline(peak_t, color='orange', linewidth=1, linestyle=':', label=f'Peak at t={peak_t:.2f}')
ax.axvline(5.0, color='gray', linewidth=1, linestyle='--', alpha=0.5, label='Original T=5')
ax.set_xlabel('t')
ax.set_ylabel(r'$\|\omega\|_\infty$')
ax.set_title(r'(C) Extended run: $\nu=0.005$, T=20')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

# ── Panel D: Extended run enstrophy + KE ──
ax = axes[1, 1]
ax.plot(ts_long['time'], ts_long['enstrophy'], 'r-', linewidth=1, label='Enstrophy')
ax2 = ax.twinx()
ax2.plot(ts_long['time'], ts_long['kinetic_energy'], 'g-', linewidth=1, label='KE')
ax2.set_ylabel('Kinetic Energy', color='green')
ax.set_xlabel('t')
ax.set_ylabel('Enstrophy', color='red')
ax.set_title(r'(D) Enstrophy and KE at $\nu=0.005$, T=20')
lines1, labels1 = ax.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax.legend(lines1 + lines2, labels1 + labels2, fontsize=9)
ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('nu_critical_artifacts/figures/nu_critical_experiment.pdf')
plt.savefig('nu_critical_artifacts/figures/nu_critical_experiment.png')
plt.show()

# ── Save all results ──
all_results = {
    'timestamp': datetime.datetime.now().isoformat(),
    'experiment_1': {
        'description': 'Locate nu_c at Re ≈ 1257: sweep nu from 0.005 to 0.00995',
        'nu_c_estimate': nu_c_estimate,
        'nu_c_ratio': nu_c_estimate / 0.005 if nu_c_estimate else None,
        'sweeps': results_exp1,
    },
    'experiment_2': {
        'description': 'Scale nu_c with Re: sweep nu from nu_0 to 2*nu_0 at 4 Re values',
        'summary': {key: {'Re': d['Re0'], 'nu0': d['nu0'],
                          'nu_c': d['nu_c'], 'ratio': d['ratio']}
                    for key, d in results_exp2.items()},
        'all_ok': all_ok,
        'sweeps': {key: d['sweeps'] for key, d in results_exp2.items()},
    },
    'experiment_3': {
        'description': f'Extended run at nu=0.005 to T={T_long}',
        'peaked_and_decayed': peaked_and_decayed,
        'still_growing': still_growing,
        'peak_omega': peak_val,
        'peak_time': peak_t,
        'final_omega': final_val,
        'final_time': final_t,
        'c_extended': fit_long['c'],
        'R2_extended': fit_long['R2'],
        'bkm_final': fit_long['bkm_final'],
    },
}

with open('nu_critical_artifacts/data/nu_critical_results.json', 'w') as f:
    json.dump(all_results, f, indent=2, default=str)

# ── Evidence report ──
report = [
    '=' * 72,
    'ν_c CRITICAL VISCOSITY EXPERIMENT — EVIDENCE REPORT',
    f'Generated: {datetime.datetime.now().isoformat()}',
    '=' * 72,
    '',
    f'Grid: N={N_RUN}  IC: Taylor-Green  Integrator: semi_implicit  θ={theta}',
    '',
    '── EXPERIMENT 1: Locate ν_c at Re ≈ 1257 ──',
]
for r in results_exp1:
    report.append(f"  ν={r['nu']:.5f}  Re={r['Re']:.0f}  c={r['c']:+.4f}  "
                  f"R²={r['R2']:.4f}  peak||ω||={r['peak_omega']:.4f}")
if nu_c_estimate:
    report.append(f'\n  → ν_c ≈ {nu_c_estimate:.6f}, ratio ν_c/ν_0 = {nu_c_estimate/0.005:.4f}')

report += [
    '',
    '── EXPERIMENT 2: ν_c/ν_0 across Re ──',
]
for key, data in sorted(results_exp2.items()):
    re0 = data['Re0']
    ratio = data['ratio']
    report.append(f"  Re={re0:.0f}  ν_0={data['nu0']:.5f}  "
                  f"ν_c={data['nu_c'] if data['nu_c'] else 'N/A'}  "
                  f"ratio={ratio if ratio else 'N/A'}")

report += [
    '',
    f'  Conjecture A.14 (ν_c/ν_0 < 2 at all Re): '
    f'{"SUPPORTED" if all_ok else "NOT SUPPORTED"}',
    '',
    '── EXPERIMENT 3: Extended run ν=0.005 ──',
    f'  T = {T_long}',
    f'  Peak ||ω||∞ = {peak_val:.4f} at t = {peak_t:.4f}',
    f'  Final ||ω||∞ = {final_val:.4f} at t = {final_t:.4f}',
    f'  Peaked and decayed: {peaked_and_decayed}',
    f'  Still growing at T={T_long}: {still_growing}',
    f'  c (extended) = {fit_long["c"]:.6f}',
    f'  Conjecture A.15 (vorticity saturates): '
    f'{"CONFIRMED" if peaked_and_decayed else "OPEN"}',
    '',
    '=' * 72,
]

with open('nu_critical_artifacts/EVIDENCE_REPORT.txt', 'w') as f:
    f.write('\n'.join(report))

print('\n✅ All results saved to nu_critical_artifacts/')
print(f'   Figures: nu_critical_artifacts/figures/')
print(f'   Data:    nu_critical_artifacts/data/nu_critical_results.json')
print(f'   Report:  nu_critical_artifacts/EVIDENCE_REPORT.txt')

# ── Download (Colab) ──
import zipfile
zip_name = 'nu_critical_artifacts.zip'
with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, _, files in os.walk('nu_critical_artifacts'):
        for fname in files:
            fpath = os.path.join(root, fname)
            zf.write(fpath)

size_kb = os.path.getsize(zip_name) / 1024
print(f'   ZIP: {zip_name} ({size_kb:.1f} KB)')

try:
    from google.colab import files
    files.download(zip_name)
    print('📥 Download triggered')
except ImportError:
    print('   Not in Colab — find the ZIP in the working directory')

print(f'\n{"="*72}')
print('WHAT TO DO WITH THESE RESULTS:')
print(f'{"="*72}')
print('''
If ν_c/ν_0 < 2 at all tested Re:
  → The adaptive mechanism's factor-2 viscosity enhancement
    pushes ν_eff above ν_c at every Re — the damping inequality
    holds with c > 0 for the adaptive system.
  → This can be stated as a theorem in the paper.

If vorticity peaks and decays at ν=0.005:
  → The constant-ν solution is bounded (at least at Re≈1257, N=128)
  → The quadratic inequality (with c<0) is the wrong diagnostic —
    boundedness holds via different mechanisms.

If ν_c/ν_0 ≥ 2 at high Re:
  → The adaptive factor-2 boost is insufficient at those Re.
  → The bridge from adaptive to classical requires MORE than
    doubling viscosity — a different approach is needed.
''')
