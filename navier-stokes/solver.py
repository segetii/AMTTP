"""
Production-grade 3D incompressible Navier-Stokes pseudo-spectral solver
with BSDT-based adaptive viscosity and full diagnostic suite.

Framework:  ∂u/∂t + (u·∇)u = -∇p + ν(E)Δu,  ∇·u = 0
            on T³ = [0,2π]³ with periodic BCs

Adaptive viscosity:  ν(E) = ν₀ · (1 + γ*(E))
where γ*(E) = E/(E+θ) is the optimal damping from the MFLS framework.

Author: Segun Odeyemi
"""

import numpy as np
from numpy.fft import fftn, ifftn, fftfreq
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
import time
import json


# ============================================================
# Data structures
# ============================================================

@dataclass
class NSParams:
    """Navier-Stokes simulation parameters."""
    N: int = 64                    # Grid resolution (N³)
    L: float = 2 * np.pi           # Domain size
    nu_base: float = 1e-3          # Base kinematic viscosity (Re ~ 1/ν)
    dt: float = 1e-3               # Time step
    T_final: float = 10.0          # End time
    theta: float = 1.0             # Adaptive damping threshold
    adaptive: bool = True          # Use adaptive viscosity
    dealiasing: bool = True        # 2/3 dealiasing rule
    integrator: str = "rk4"        # "euler", "rk2", "rk4", "etdrk4"
    diag_interval: int = 10        # Steps between fast diagnostics
    heavy_interval: int = 100      # Steps between heavy diagnostics
    save_interval: int = 500       # Steps between field saves
    cfl_target: float = 0.5        # Target CFL number for adaptive dt
    adaptive_dt: bool = False      # Use adaptive time stepping


@dataclass
class BSDTChannels:
    """BSDT channel values for a velocity field snapshot."""
    delta_C: float = 0.0   # Credit camouflage → Enstrophy growth rate
    delta_G: float = 0.0   # Feature gap → Spectral anomaly
    delta_A: float = 0.0   # Activity anomaly → Vorticity-strain alignment
    delta_T: float = 0.0   # Temporal novelty → Finite-time Lyapunov exponent
    E_bs: float = 0.0      # Composite blind-spot energy


@dataclass
class Diagnostics:
    """Full diagnostic snapshot."""
    time: float = 0.0
    step: int = 0
    # Fast diagnostics (every diag_interval steps)
    kinetic_energy: float = 0.0
    enstrophy: float = 0.0
    omega_inf: float = 0.0          # ||ω||_∞ — BKM criterion
    grad_u_L2: float = 0.0          # ||∇u||_L²
    max_velocity: float = 0.0
    # BSDT channels
    bsdt: BSDTChannels = field(default_factory=BSDTChannels)
    # Adaptive viscosity
    nu_effective: float = 0.0
    gamma_star: float = 0.0
    # Heavy diagnostics (every heavy_interval steps)
    alignment_mean: float = 0.0     # <cos θ(ω, e₁)>
    alignment_e2_mean: float = 0.0  # <cos θ(ω, e₂)> — depletion indicator
    max_stretching: float = 0.0     # max(ωᵀSω)
    strain_eigenvalue_max: float = 0.0
    spectral_slope: float = 0.0     # Energy spectrum power law exponent
    condition_number: float = 0.0   # κ(Σ) — separation condition
    # Derived quantities
    R_ratio: float = 0.0           # max λ₁ / (ν ||∇u||_L²)
    bkm_integral: float = 0.0     # Running ∫₀ᵗ ||ω||_∞ ds


@dataclass
class SimulationState:
    """Complete simulation state."""
    u_hat: np.ndarray = None       # Fourier-space velocity (3, N, N, N) complex
    t: float = 0.0
    step: int = 0
    diagnostics_history: List = field(default_factory=list)
    bkm_integral: float = 0.0


# ============================================================
# Grid and wavenumber setup
# ============================================================

class SpectralGrid:
    """Manages the spectral grid, wavenumbers, and dealiasing."""

    def __init__(self, params: NSParams):
        self.N = params.N
        self.L = params.L
        self.dealiasing = params.dealiasing

        # Physical grid
        dx = self.L / self.N
        x = np.linspace(0, self.L, self.N, endpoint=False)
        self.X, self.Y, self.Z = np.meshgrid(x, x, x, indexing='ij')

        # Wavenumbers
        k = fftfreq(self.N, d=1.0/self.N) * (2 * np.pi / self.L)
        self.KX, self.KY, self.KZ = np.meshgrid(k, k, k, indexing='ij')
        self.K2 = self.KX**2 + self.KY**2 + self.KZ**2
        self.K2_safe = self.K2.copy()
        self.K2_safe[0, 0, 0] = 1.0  # Avoid division by zero
        self.K_mag = np.sqrt(self.K2)

        # Dealiasing mask (2/3 rule)
        if self.dealiasing:
            k_max = self.N // 3
            self.mask = np.ones((self.N, self.N, self.N), dtype=bool)
            for kk in [self.KX, self.KY, self.KZ]:
                kk_abs = np.abs(kk) * self.L / (2 * np.pi)
                self.mask &= (kk_abs <= k_max)
        else:
            self.mask = np.ones((self.N, self.N, self.N), dtype=bool)

        # Shell indices for energy spectrum
        self.k_shells = np.arange(0, self.N // 2)
        self.shell_idx = np.round(self.K_mag * self.L / (2 * np.pi)).astype(int)

    def project_divergence_free(self, u_hat):
        """Leray projection: remove divergent component."""
        k_dot_u = (self.KX * u_hat[0] +
                   self.KY * u_hat[1] +
                   self.KZ * u_hat[2])
        u_hat[0] -= self.KX * k_dot_u / self.K2_safe
        u_hat[1] -= self.KY * k_dot_u / self.K2_safe
        u_hat[2] -= self.KZ * k_dot_u / self.K2_safe
        # Zero out the zero mode pressure
        u_hat[:, 0, 0, 0] = 0
        return u_hat

    def dealias(self, u_hat):
        """Apply 2/3 dealiasing."""
        if self.dealiasing:
            u_hat[:, ~self.mask] = 0
        return u_hat

    def energy_spectrum(self, u_hat):
        """Shell-averaged energy spectrum E(k)."""
        E_k = 0.5 * np.sum(np.abs(u_hat)**2, axis=0) / self.N**6
        spectrum = np.zeros(self.N // 2)
        for k_idx in range(self.N // 2):
            shell = (self.shell_idx == k_idx)
            if np.any(shell):
                spectrum[k_idx] = np.sum(E_k[shell])
        return spectrum


# ============================================================
# Initial conditions
# ============================================================

def taylor_green_vortex(grid: SpectralGrid) -> np.ndarray:
    """Taylor-Green vortex: classic test case for potential blow-up.
    Known exact solution at t=0, develops complex vortex dynamics."""
    u = np.zeros((3, grid.N, grid.N, grid.N))
    u[0] = np.sin(grid.X) * np.cos(grid.Y) * np.cos(grid.Z)
    u[1] = -np.cos(grid.X) * np.sin(grid.Y) * np.cos(grid.Z)
    u[2] = 0.0
    u_hat = fftn(u, axes=(1, 2, 3))
    u_hat = grid.project_divergence_free(u_hat)
    u_hat = grid.dealias(u_hat)
    return u_hat


def abc_flow(grid: SpectralGrid, A=1.0, B=1.0, C=1.0) -> np.ndarray:
    """Arnold-Beltrami-Childress flow: chaotic streamlines, Beltrami flow."""
    u = np.zeros((3, grid.N, grid.N, grid.N))
    u[0] = A * np.sin(grid.Z) + C * np.cos(grid.Y)
    u[1] = B * np.sin(grid.X) + A * np.cos(grid.Z)
    u[2] = C * np.sin(grid.Y) + B * np.cos(grid.X)
    u_hat = fftn(u, axes=(1, 2, 3))
    u_hat = grid.project_divergence_free(u_hat)
    u_hat = grid.dealias(u_hat)
    return u_hat


def kida_vortex(grid: SpectralGrid) -> np.ndarray:
    """Kida vortex: known to produce intense vortex stretching."""
    u = np.zeros((3, grid.N, grid.N, grid.N))
    u[0] = np.sin(grid.X) * (np.cos(3*grid.Y) * np.cos(grid.Z) -
                               np.cos(grid.Y) * np.cos(3*grid.Z))
    u[1] = np.sin(grid.Y) * (np.cos(3*grid.Z) * np.cos(grid.X) -
                               np.cos(grid.Z) * np.cos(3*grid.X))
    u[2] = np.sin(grid.Z) * (np.cos(3*grid.X) * np.cos(grid.Y) -
                               np.cos(grid.X) * np.cos(3*grid.Y))
    u_hat = fftn(u, axes=(1, 2, 3))
    u_hat = grid.project_divergence_free(u_hat)
    u_hat = grid.dealias(u_hat)
    return u_hat


def random_divergence_free(grid: SpectralGrid, seed=42, energy_scale=1.0) -> np.ndarray:
    """Random divergence-free field with prescribed energy spectrum."""
    rng = np.random.RandomState(seed)
    u_hat = (rng.randn(3, grid.N, grid.N, grid.N) +
             1j * rng.randn(3, grid.N, grid.N, grid.N))
    # Apply k^{-5/3} energy spectrum
    k_mag = np.maximum(grid.K_mag, 1e-10)
    envelope = energy_scale * k_mag**(-5.0/6.0) * np.exp(-k_mag**2 / (grid.N/3)**2)
    u_hat *= envelope[np.newaxis, :]
    u_hat = grid.project_divergence_free(u_hat)
    u_hat = grid.dealias(u_hat)
    return u_hat


INITIAL_CONDITIONS = {
    "taylor_green": taylor_green_vortex,
    "abc": abc_flow,
    "kida": kida_vortex,
    "random": random_divergence_free,
}


# ============================================================
# BSDT Operators for Velocity Fields
# ============================================================

class BSDTOperatorNS:
    """
    Blind-Spot Detection Theory operators adapted for the
    Navier-Stokes velocity field.

    Maps the 4 BSDT channels to fluid mechanical quantities:
      δ_C → Enstrophy growth anomaly (Mahalanobis-type)
      δ_G → Spectral gap (departure from Kolmogorov cascade)
      δ_A → Vorticity-strain alignment (depletion of nonlinearity)
      δ_T → Temporal novelty (FTLE-based)
    """

    def __init__(self, grid: SpectralGrid, params: NSParams):
        self.grid = grid
        self.params = params
        # Reference statistics (calibrated on "normal" period)
        self._enstrophy_history = []
        self._spectrum_history = []
        self._alignment_history = []
        self._calibrated = False
        self._ref_enstrophy_mean = 0.0
        self._ref_enstrophy_std = 1.0
        self._ref_spectrum = None
        self._ref_alignment_mean = 0.0
        self._ref_alignment_std = 1.0
        self._prev_u_hat = None

    def calibrate(self, enstrophy_series, spectrum_series, alignment_series):
        """Calibrate reference statistics from a 'normal' period."""
        self._ref_enstrophy_mean = np.mean(enstrophy_series)
        self._ref_enstrophy_std = max(np.std(enstrophy_series), 1e-10)
        self._ref_spectrum = np.mean(spectrum_series, axis=0)
        self._ref_alignment_mean = np.mean(alignment_series)
        self._ref_alignment_std = max(np.std(alignment_series), 1e-10)
        self._calibrated = True

    def compute_all(self, u_hat, u_real, omega, S, enstrophy,
                    spectrum, alignment_mean) -> BSDTChannels:
        """Compute all 4 BSDT channels."""
        channels = BSDTChannels()

        # δ_C: Enstrophy growth anomaly (Mahalanobis-type distance)
        channels.delta_C = self._delta_C(enstrophy)

        # δ_G: Spectral gap (departure from Kolmogorov k^{-5/3})
        channels.delta_G = self._delta_G(spectrum)

        # δ_A: Activity anomaly / vorticity-strain alignment
        channels.delta_A = self._delta_A(alignment_mean)

        # δ_T: Temporal novelty (change from previous state)
        channels.delta_T = self._delta_T(u_hat)

        # Composite blind-spot energy
        channels.E_bs = (channels.delta_C**2 + channels.delta_G**2 +
                         channels.delta_A**2 + channels.delta_T**2)

        self._prev_u_hat = u_hat.copy()
        return channels

    def _delta_C(self, enstrophy: float) -> float:
        """δ_C: How far is current enstrophy from the reference distribution?
        Analogous to Mahalanobis distance of credit metrics."""
        if not self._calibrated:
            self._enstrophy_history.append(enstrophy)
            if len(self._enstrophy_history) > 10:
                mean = np.mean(self._enstrophy_history)
                std = max(np.std(self._enstrophy_history), 1e-10)
                return abs(enstrophy - mean) / std
            return 0.0
        return abs(enstrophy - self._ref_enstrophy_mean) / self._ref_enstrophy_std

    def _delta_G(self, spectrum: np.ndarray) -> float:
        """δ_G: How far is the energy spectrum from Kolmogorov k^{-5/3}?
        Analogous to PCA residual (feature gap)."""
        k = np.arange(1, len(spectrum))
        E_k = spectrum[1:]
        # Fit k^{-5/3} reference
        valid = E_k > 1e-20
        if np.sum(valid) < 3:
            return 0.0
        log_k = np.log(k[valid])
        log_E = np.log(E_k[valid])
        # Kolmogorov prediction
        if self._ref_spectrum is not None and self._calibrated:
            ref = self._ref_spectrum[1:]
            ref_valid = ref[valid]
            ref_valid = np.maximum(ref_valid, 1e-20)
            residual = np.sum((log_E - np.log(ref_valid))**2)
        else:
            # Compare to k^{-5/3}
            slope = -5.0 / 3.0
            intercept = np.mean(log_E - slope * log_k)
            predicted = slope * log_k + intercept
            residual = np.sum((log_E - predicted)**2)
        return np.sqrt(residual / len(log_k))

    def _delta_A(self, alignment_mean: float) -> float:
        """δ_A: Vorticity-strain alignment anomaly.
        LOW alignment is actually NORMAL (depletion).
        HIGH alignment is DANGEROUS (approaching blow-up).
        Analogous to activity anomaly — 'calm before storm'."""
        if not self._calibrated:
            self._alignment_history.append(alignment_mean)
            if len(self._alignment_history) > 10:
                mean = np.mean(self._alignment_history)
                std = max(np.std(self._alignment_history), 1e-10)
                # Negative sign: DECREASED alignment is the warning
                # (just like δ_A in financial framework)
                return -(alignment_mean - mean) / std
            return 0.0
        return -(alignment_mean - self._ref_alignment_mean) / self._ref_alignment_std

    def _delta_T(self, u_hat: np.ndarray) -> float:
        """δ_T: Temporal novelty — how different is current state from previous?
        Analogous to KDE self-history novelty."""
        if self._prev_u_hat is None:
            return 0.0
        diff = u_hat - self._prev_u_hat
        novelty = np.sqrt(np.sum(np.abs(diff)**2) / np.sum(np.abs(u_hat)**2 + 1e-20))
        return novelty


# ============================================================
# Adaptive Viscosity (from MFLS framework)
# ============================================================

class AdaptiveViscosity:
    """
    State-dependent viscosity from the MFLS optimal damping law.

    ν(E) = ν₀ · (1 + γ*(E))

    where γ*(E) = E / (E + θ)  is the optimal damping from Theorem OR2.

    Key properties:
    - When E → 0 (system near equilibrium): ν(E) → ν₀ (standard NS)
    - When E → ∞ (blow-up imminent): ν(E) → 2ν₀ (maximum regularisation)
    - The transition is smooth and the derivative γ*'(E) > 0

    This is a NEW member of the Ladyzhenskaya regularisation family
    where viscosity depends on a GLOBAL functional (E_BS) rather than
    local gradients.
    """

    def __init__(self, nu_base: float, theta: float, adaptive: bool = True):
        self.nu_base = nu_base
        self.theta = theta
        self.adaptive = adaptive

    def gamma_star(self, E_bs: float) -> float:
        """Optimal damping coefficient γ*(E) = E/(E+θ)."""
        if not self.adaptive:
            return 0.0
        return E_bs / (E_bs + self.theta)

    def nu_effective(self, E_bs: float) -> float:
        """Effective viscosity ν(E) = ν₀(1 + γ*(E))."""
        return self.nu_base * (1.0 + self.gamma_star(E_bs))

    def spectral_viscosity(self, E_bs: float, K2: np.ndarray) -> np.ndarray:
        """Full spectral viscosity operator for time stepping.
        Returns exp(-ν(E)·|k|²·dt) for the integrating factor."""
        nu = self.nu_effective(E_bs)
        return nu * K2


# ============================================================
# Core Solver
# ============================================================

class NavierStokesSolver:
    """
    3D incompressible NS solver with BSDT diagnostics.

    Pseudo-spectral method with:
    - Leray projection (exact divergence-free)
    - 2/3 dealiasing
    - RK4 or ETDRK4 time integration
    - Adaptive viscosity ν(E_BS)
    - Full BSDT channel diagnostics
    """

    def __init__(self, params: NSParams):
        self.params = params
        self.grid = SpectralGrid(params)
        self.viscosity = AdaptiveViscosity(params.nu_base, params.theta,
                                           params.adaptive)
        self.bsdt = BSDTOperatorNS(self.grid, params)
        self.state = SimulationState()

    def initialize(self, ic_name: str = "taylor_green", **kwargs):
        """Set initial condition."""
        ic_func = INITIAL_CONDITIONS[ic_name]
        self.state.u_hat = ic_func(self.grid, **kwargs)
        self.state.t = 0.0
        self.state.step = 0
        self.state.diagnostics_history = []
        self.state.bkm_integral = 0.0
        print(f"Initialized: {ic_name}, N={self.params.N}, "
              f"ν={self.params.nu_base:.1e}, "
              f"adaptive={'ON' if self.params.adaptive else 'OFF'}, "
              f"θ={self.params.theta}")

    def _compute_rhs(self, u_hat: np.ndarray, nu_eff: float) -> np.ndarray:
        """Compute right-hand side: -P[(u·∇)u] + ν Δu."""
        g = self.grid

        # Transform to physical space
        u = np.real(ifftn(u_hat, axes=(1, 2, 3)))

        # Compute velocity gradients in spectral space
        # ∂u_i/∂x_j via i·k_j·û_i
        grad_u_hat = np.zeros((3, 3, g.N, g.N, g.N), dtype=complex)
        for i in range(3):
            grad_u_hat[i, 0] = 1j * g.KX * u_hat[i]
            grad_u_hat[i, 1] = 1j * g.KY * u_hat[i]
            grad_u_hat[i, 2] = 1j * g.KZ * u_hat[i]

        # Compute (u·∇)u in physical space (dealiased)
        grad_u = np.real(ifftn(grad_u_hat, axes=(2, 3, 4)))
        nonlinear = np.zeros_like(u)
        for i in range(3):
            for j in range(3):
                nonlinear[i] += u[j] * grad_u[i, j]

        # Transform nonlinear term to spectral space
        nonlinear_hat = fftn(nonlinear, axes=(1, 2, 3))

        # Leray projection: remove pressure gradient
        nonlinear_hat = g.project_divergence_free(nonlinear_hat)

        # Dealiasing
        nonlinear_hat = g.dealias(nonlinear_hat)

        # Viscous term: ν Δu = -ν|k|²û
        viscous = -nu_eff * g.K2[np.newaxis, :] * u_hat

        # RHS = -nonlinear + viscous
        return -nonlinear_hat + viscous

    def _step_rk4(self, E_bs: float):
        """4th-order Runge-Kutta time step."""
        dt = self.params.dt
        u = self.state.u_hat
        nu = self.viscosity.nu_effective(E_bs)

        k1 = self._compute_rhs(u, nu)
        k2 = self._compute_rhs(u + 0.5 * dt * k1, nu)
        k3 = self._compute_rhs(u + 0.5 * dt * k2, nu)
        k4 = self._compute_rhs(u + dt * k3, nu)

        self.state.u_hat = u + (dt / 6.0) * (k1 + 2*k2 + 2*k3 + k4)

        # Enforce divergence-free and dealiasing
        self.state.u_hat = self.grid.project_divergence_free(self.state.u_hat)
        self.state.u_hat = self.grid.dealias(self.state.u_hat)

    def _step_euler(self, E_bs: float):
        """Forward Euler (for debugging only)."""
        dt = self.params.dt
        nu = self.viscosity.nu_effective(E_bs)
        rhs = self._compute_rhs(self.state.u_hat, nu)
        self.state.u_hat += dt * rhs
        self.state.u_hat = self.grid.project_divergence_free(self.state.u_hat)
        self.state.u_hat = self.grid.dealias(self.state.u_hat)

    def _step_semi_implicit(self, E_bs: float):
        """Semi-implicit: exact viscous integration + explicit nonlinear.
        More stable than pure explicit for stiff viscous terms."""
        dt = self.params.dt
        nu = self.viscosity.nu_effective(E_bs)
        g = self.grid

        # Integrating factor for viscous term
        integrating_factor = np.exp(-nu * g.K2 * dt)

        # Compute nonlinear term at current state
        u = np.real(ifftn(self.state.u_hat, axes=(1, 2, 3)))

        grad_u_hat = np.zeros((3, 3, g.N, g.N, g.N), dtype=complex)
        for i in range(3):
            grad_u_hat[i, 0] = 1j * g.KX * self.state.u_hat[i]
            grad_u_hat[i, 1] = 1j * g.KY * self.state.u_hat[i]
            grad_u_hat[i, 2] = 1j * g.KZ * self.state.u_hat[i]

        grad_u = np.real(ifftn(grad_u_hat, axes=(2, 3, 4)))
        nonlinear = np.zeros_like(u)
        for i in range(3):
            for j in range(3):
                nonlinear[i] += u[j] * grad_u[i, j]

        nonlinear_hat = fftn(nonlinear, axes=(1, 2, 3))
        nonlinear_hat = g.project_divergence_free(nonlinear_hat)
        nonlinear_hat = g.dealias(nonlinear_hat)

        # Semi-implicit update: û(t+dt) = IF · û(t) - dt · IF · N̂
        self.state.u_hat = (integrating_factor[np.newaxis, :] *
                            (self.state.u_hat - dt * nonlinear_hat))

        self.state.u_hat = g.project_divergence_free(self.state.u_hat)
        self.state.u_hat = g.dealias(self.state.u_hat)

    def compute_diagnostics(self, heavy: bool = False) -> Diagnostics:
        """Compute diagnostic quantities from current state."""
        g = self.grid
        diag = Diagnostics()
        diag.time = self.state.t
        diag.step = self.state.step

        # Physical-space velocity
        u = np.real(ifftn(self.state.u_hat, axes=(1, 2, 3)))

        # Velocity gradients
        grad_u_hat = np.zeros((3, 3, g.N, g.N, g.N), dtype=complex)
        for i in range(3):
            grad_u_hat[i, 0] = 1j * g.KX * self.state.u_hat[i]
            grad_u_hat[i, 1] = 1j * g.KY * self.state.u_hat[i]
            grad_u_hat[i, 2] = 1j * g.KZ * self.state.u_hat[i]
        grad_u = np.real(ifftn(grad_u_hat, axes=(2, 3, 4)))

        # Vorticity ω = ∇ × u
        omega = np.array([
            grad_u[2, 1] - grad_u[1, 2],
            grad_u[0, 2] - grad_u[2, 0],
            grad_u[1, 0] - grad_u[0, 1]
        ])
        omega_mag = np.sqrt(np.sum(omega**2, axis=0))

        # Strain tensor S = ½(∇u + ∇uᵀ)
        S = 0.5 * (grad_u + np.swapaxes(grad_u, 0, 1))

        # Fast diagnostics
        diag.kinetic_energy = 0.5 * np.mean(np.sum(u**2, axis=0))
        diag.enstrophy = 0.5 * np.mean(np.sum(omega**2, axis=0))
        diag.omega_inf = np.max(omega_mag)
        diag.grad_u_L2 = np.sqrt(np.mean(np.sum(grad_u**2, axis=(0, 1))))
        diag.max_velocity = np.max(np.sqrt(np.sum(u**2, axis=0)))

        # BKM integral: ∫₀ᵗ ||ω||_∞ ds
        self.state.bkm_integral += diag.omega_inf * self.params.dt * self.params.diag_interval
        diag.bkm_integral = self.state.bkm_integral

        # Energy spectrum
        spectrum = g.energy_spectrum(self.state.u_hat)

        # BSDT channels
        alignment_mean = 0.0
        if heavy:
            # Heavy diagnostics: subsampled alignment computation
            N = g.N
            n_samples = max(100, N**3 // 100)  # ~1% of grid
            rng = np.random.RandomState(self.state.step)
            indices = rng.randint(0, N, size=(n_samples, 3))

            align_e1_vals = []
            align_e2_vals = []
            stretching_vals = []
            strain_eigmax_vals = []

            for idx in indices:
                i, j, k = idx
                w = omega[:, i, j, k]
                w_norm = np.linalg.norm(w)
                if w_norm < 1e-12:
                    continue

                S_loc = S[:, :, i, j, k]
                try:
                    eigvals, eigvecs = np.linalg.eigh(S_loc)
                except:
                    continue
                # Sort: λ₁ ≥ λ₂ ≥ λ₃
                order = np.argsort(eigvals)[::-1]
                eigvals = eigvals[order]
                eigvecs = eigvecs[:, order]

                # Alignment with e₁ (max stretching direction)
                cos_e1 = abs(np.dot(w, eigvecs[:, 0])) / w_norm
                align_e1_vals.append(cos_e1)

                # Alignment with e₂ (intermediate) — DEPLETION indicator
                cos_e2 = abs(np.dot(w, eigvecs[:, 1])) / w_norm
                align_e2_vals.append(cos_e2)

                # Local stretching: ωᵀSω
                stretching = w @ S_loc @ w
                stretching_vals.append(stretching)

                strain_eigmax_vals.append(eigvals[0])

            if align_e1_vals:
                diag.alignment_mean = np.mean(align_e1_vals)
                diag.alignment_e2_mean = np.mean(align_e2_vals)
                diag.max_stretching = np.max(stretching_vals)
                diag.strain_eigenvalue_max = np.max(strain_eigmax_vals)
                alignment_mean = diag.alignment_mean

            # Spectral slope (inertial range)
            k_range = spectrum[2:g.N//4]
            k_vals = np.arange(2, g.N//4)
            valid = k_range > 1e-20
            if np.sum(valid) > 2:
                log_k = np.log(k_vals[valid])
                log_E = np.log(k_range[valid])
                slope, _ = np.polyfit(log_k, log_E, 1)
                diag.spectral_slope = slope

            # Condition number of velocity covariance (Separation condition)
            # Σ = <u ⊗ u> spatially averaged
            u_flat = u.reshape(3, -1)  # (3, N³)
            cov = np.cov(u_flat)
            eigvals_cov = np.linalg.eigvalsh(cov)
            eigvals_cov = np.abs(eigvals_cov)
            if eigvals_cov[-1] > 1e-15:
                diag.condition_number = eigvals_cov[-1] / max(eigvals_cov[0], 1e-15)

        # BSDT channels
        bsdt_channels = self.bsdt.compute_all(
            self.state.u_hat, u, omega, S,
            diag.enstrophy, spectrum, alignment_mean
        )
        diag.bsdt = bsdt_channels

        # Adaptive viscosity state
        E_bs = bsdt_channels.E_bs
        diag.gamma_star = self.viscosity.gamma_star(E_bs)
        diag.nu_effective = self.viscosity.nu_effective(E_bs)

        # R ratio: max_λ₁ / (ν ||∇u||_L²) — blow-up indicator
        if diag.nu_effective > 0 and diag.grad_u_L2 > 0:
            lambda_max = diag.strain_eigenvalue_max if heavy else 0
            diag.R_ratio = lambda_max / (diag.nu_effective * diag.grad_u_L2)

        return diag

    def run(self, progress_callback=None):
        """Run the full simulation."""
        p = self.params
        total_steps = int(p.T_final / p.dt)

        print(f"\nRunning NS solver: {total_steps} steps, T={p.T_final}")
        print(f"{'Step':>8} {'Time':>8} {'Energy':>10} {'Enstrophy':>12} "
              f"{'||ω||∞':>10} {'ν_eff':>10} {'γ*':>8} {'E_BS':>10} "
              f"{'δ_A':>8} {'BKM∫':>10}")
        print("-" * 110)

        t_start = time.time()
        E_bs_current = 0.0

        for step in range(total_steps):
            self.state.step = step
            self.state.t = step * p.dt

            # Diagnostics
            do_diag = (step % p.diag_interval == 0)
            do_heavy = (step % p.heavy_interval == 0)

            if do_diag:
                diag = self.compute_diagnostics(heavy=do_heavy)
                E_bs_current = diag.bsdt.E_bs
                self.state.diagnostics_history.append(diag)

                if step % (p.diag_interval * 10) == 0:
                    print(f"{step:8d} {diag.time:8.4f} {diag.kinetic_energy:10.6f} "
                          f"{diag.enstrophy:12.6f} {diag.omega_inf:10.4f} "
                          f"{diag.nu_effective:10.6f} {diag.gamma_star:8.4f} "
                          f"{diag.bsdt.E_bs:10.4f} {diag.bsdt.delta_A:8.4f} "
                          f"{diag.bkm_integral:10.4f}")

                # Blow-up detection
                if diag.enstrophy > 1e12 or np.isnan(diag.enstrophy):
                    print(f"\n*** BLOW-UP DETECTED at t={diag.time:.6f} ***")
                    print(f"    Enstrophy = {diag.enstrophy:.2e}")
                    print(f"    ||ω||_∞ = {diag.omega_inf:.2e}")
                    print(f"    BKM integral = {diag.bkm_integral:.6f}")
                    break

            # Time step
            if p.integrator == "rk4":
                self._step_rk4(E_bs_current)
            elif p.integrator == "semi_implicit":
                self._step_semi_implicit(E_bs_current)
            else:
                self._step_euler(E_bs_current)

            if progress_callback:
                progress_callback(step, total_steps)

        elapsed = time.time() - t_start
        print(f"\nCompleted in {elapsed:.1f}s ({total_steps/elapsed:.0f} steps/s)")
        return self.state.diagnostics_history


# ============================================================
# Analysis tools
# ============================================================

def compare_adaptive_vs_constant(params_base: NSParams, ic_name: str = "taylor_green"):
    """
    THE CRITICAL EXPERIMENT:
    Run identical simulation with constant ν vs adaptive ν(E).
    Compare enstrophy growth, BKM integral, and blow-up time.
    """
    results = {}

    for label, adaptive in [("constant_nu", False), ("adaptive_nu", True)]:
        print(f"\n{'='*60}")
        print(f"  Running: {label}")
        print(f"{'='*60}")

        params = NSParams(
            N=params_base.N,
            L=params_base.L,
            nu_base=params_base.nu_base,
            dt=params_base.dt,
            T_final=params_base.T_final,
            theta=params_base.theta,
            adaptive=adaptive,
            dealiasing=params_base.dealiasing,
            integrator=params_base.integrator,
            diag_interval=params_base.diag_interval,
            heavy_interval=params_base.heavy_interval,
        )

        solver = NavierStokesSolver(params)
        solver.initialize(ic_name)
        history = solver.run()
        results[label] = history

    return results


def extract_timeseries(history):
    """Extract numpy arrays from diagnostic history."""
    data = {}
    data['time'] = np.array([d.time for d in history])
    data['energy'] = np.array([d.kinetic_energy for d in history])
    data['enstrophy'] = np.array([d.enstrophy for d in history])
    data['omega_inf'] = np.array([d.omega_inf for d in history])
    data['grad_u_L2'] = np.array([d.grad_u_L2 for d in history])
    data['nu_eff'] = np.array([d.nu_effective for d in history])
    data['gamma_star'] = np.array([d.gamma_star for d in history])
    data['E_bs'] = np.array([d.bsdt.E_bs for d in history])
    data['delta_C'] = np.array([d.bsdt.delta_C for d in history])
    data['delta_G'] = np.array([d.bsdt.delta_G for d in history])
    data['delta_A'] = np.array([d.bsdt.delta_A for d in history])
    data['delta_T'] = np.array([d.bsdt.delta_T for d in history])
    data['bkm_integral'] = np.array([d.bkm_integral for d in history])
    data['alignment_mean'] = np.array([d.alignment_mean for d in history])
    data['alignment_e2'] = np.array([d.alignment_e2_mean for d in history])
    data['max_stretching'] = np.array([d.max_stretching for d in history])
    data['condition_number'] = np.array([d.condition_number for d in history])
    data['R_ratio'] = np.array([d.R_ratio for d in history])
    return data


def save_results(results: dict, filename: str):
    """Save results to JSON."""
    output = {}
    for label, history in results.items():
        data = extract_timeseries(history)
        output[label] = {k: v.tolist() for k, v in data.items()}
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"Results saved to {filename}")
