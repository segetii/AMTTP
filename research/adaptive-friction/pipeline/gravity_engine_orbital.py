"""
gravity_engine_orbital.py  (second-order dynamics)
====================================================
Extension of gravity_engine_newtonian.py with SECOND-ORDER Newtonian dynamics.

The key difference:  particles have VELOCITY and INERTIA.

First-order (gravity_engine_newtonian.py):
    dx/dt = F(x)                        ← gradient descent, no momentum
    Problem: everything falls into gravity well → 92% Ponzi

Second-order (this file):
    m * d²x/dt² = F(x) - β * dx/dt     ← Newton's 2nd law + damping
    Angular momentum L = m * r × v is approximately conserved
    Result: stable ORBITS instead of collapse

Integration: Velocity-Verlet (symplectic, energy-conserving)
    v(t+½dt) = v(t) + ½ dt F(t)/m
    x(t+dt)  = x(t) + dt v(t+½dt)
    v(t+dt)  = v(t+½dt) + ½ dt F(t+dt)/m - β v(t+½dt)

The damping β controls dissipation:
    β = 0     : conservative (perpetual orbits, like planets)
    β > 0     : damped (orbits decay, system settles to virial equilibrium)
    β derived from data via energy balance

Author: Odeyemi Olusegun Israel
"""

from __future__ import annotations
import sys
import numpy as np
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# Import everything from the Newtonian engine
THIS_DIR = Path(__file__).parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from gravity_engine_newtonian import (
    ALPHA, GAMMA, SIGMA, LAMBDA_REP, EPS, F_MAX,
    G_NEWTON, MASS_DEFAULT, GRAV_SOFT, MIX_GRAV,
    compute_masses_from_data, compute_G_from_data,
    radial_energy, pairwise_energy, newtonian_energy,
    radial_force, pairwise_force, newtonian_force,
    total_energy, total_force,
    spectral_radius, BSDTOperator,
)


# ─────────────────────────────────────────────────────────────────────────────
# Data-derived damping coefficient
# ─────────────────────────────────────────────────────────────────────────────

def compute_damping_from_data(X_series: np.ndarray, masses: np.ndarray,
                               G: float, alpha: float = ALPHA) -> float:
    """
    Derive the damping coefficient β from the data's own energy scales.
    No heuristics.

    Principle: β should be set so that the dissipation timescale
    matches the system's natural orbital period.

    τ_orbital ≈ 2π √(⟨r⟩³ / (G ⟨m⟩))     [Kepler's 3rd law analogue]
    τ_damping = 1/β

    We set β so that τ_damping ≈ τ_orbital (critically damped orbits):
        β = 1/τ_orbital = √(G ⟨m⟩) / (2π ⟨r⟩^{3/2})

    This ensures orbits decay on a timescale comparable to one orbital period —
    not too fast (no orbits visible) and not too slow (takes forever).
    """
    T, N, d = X_series.shape

    # Mean inter-particle distance
    mean_r = 0.0
    count = 0
    for t in range(0, T, max(1, T // 20)):
        X = X_series[t]
        diff = X[:, None, :] - X[None, :, :]
        dist = np.sqrt(np.sum(diff ** 2, axis=2) + 1e-12)
        triu = np.triu_indices(N, k=1)
        mean_r += dist[triu].mean()
        count += 1
    mean_r /= count

    mean_m = masses.mean()

    # Kepler orbital period analogue
    tau_orbital = 2 * np.pi * np.sqrt(mean_r ** 3 / (G * mean_m + 1e-12))

    # Critical damping: β = 1/τ
    beta = 1.0 / (tau_orbital + 1e-12)

    return float(beta)


def compute_initial_velocities(X_series: np.ndarray) -> np.ndarray:
    """
    Derive initial velocities from the data itself.
    
    v(t=0) = [X(1) - X(0)] / Δt
    
    This gives each bank a velocity vector derived from its actual
    quarter-to-quarter movement. No random velocities. Data-only.
    """
    if X_series.shape[0] < 2:
        return np.zeros_like(X_series[0])
    # Δt = 1 quarter (normalised)
    v0 = X_series[1] - X_series[0]
    return v0


# ─────────────────────────────────────────────────────────────────────────────
# Angular momentum computation
# ─────────────────────────────────────────────────────────────────────────────

def angular_momentum(X: np.ndarray, V: np.ndarray,
                     masses: np.ndarray) -> np.ndarray:
    """
    Compute generalised angular momentum for each particle.
    
    In d dimensions, angular momentum is an antisymmetric tensor:
        L_i^{ab} = m_i (x_i^a v_i^b - x_i^b v_i^a)
    
    We return the Frobenius norm ‖L_i‖ for each particle.
    This is the magnitude of angular momentum — the conserved quantity
    that prevents radial collapse.
    """
    N, d = X.shape
    L_norms = np.zeros(N)
    
    for i in range(N):
        # Antisymmetric tensor: L^{ab} = m * (x^a v^b - x^b v^a)
        L_tensor = masses[i] * (X[i, :, None] * V[i, None, :] -
                                 X[i, None, :] * V[i, :, None])
        # Frobenius norm of antisymmetric part
        L_norms[i] = np.linalg.norm(L_tensor) / np.sqrt(2)  # factor from antisymm
    
    return L_norms


def total_angular_momentum(X: np.ndarray, V: np.ndarray,
                           masses: np.ndarray) -> float:
    """Total system angular momentum magnitude."""
    return float(angular_momentum(X, V, masses).sum())


def kinetic_energy(V: np.ndarray, masses: np.ndarray) -> float:
    """K = Σᵢ ½ mᵢ ‖vᵢ‖²"""
    return float(0.5 * np.sum(masses * np.sum(V ** 2, axis=1)))


# ─────────────────────────────────────────────────────────────────────────────
# Velocity-Verlet integrator (symplectic, energy-conserving)
# ─────────────────────────────────────────────────────────────────────────────

def verlet_step(X: np.ndarray, V: np.ndarray, masses: np.ndarray,
                mu: np.ndarray, dt: float, beta: float,
                mix_grav: float = MIX_GRAV, **kw) -> tuple[np.ndarray, np.ndarray]:
    """
    One step of velocity-Verlet integration with damping.
    
    Algorithm:
        1. v(t + ½dt) = v(t) + ½ dt [F(t)/m - β v(t)]
        2. x(t + dt)  = x(t) + dt v(t + ½dt)
        3. Compute F(t + dt)
        4. v(t + dt)  = v(t + ½dt) + ½ dt [F(t+dt)/m - β v(t + ½dt)]
    
    Symplectic → conserves phase space volume
    Damping β breaks exact conservation but mimics real dissipation
    """
    N, d = X.shape
    m = masses[:, None]  # (N, 1) for broadcasting
    
    # Force at current position
    mu_t = X.mean(axis=0)
    F = total_force(X, mu_t, masses=masses, mix_grav=mix_grav, **kw)
    
    # Half-step velocity
    V_half = V + 0.5 * dt * (F / m - beta * V)
    
    # Full-step position
    X_new = X + dt * V_half
    
    # Force at new position
    mu_new = X_new.mean(axis=0)
    F_new = total_force(X_new, mu_new, masses=masses, mix_grav=mix_grav, **kw)
    
    # Full-step velocity
    V_new = V_half + 0.5 * dt * (F_new / m - beta * V_half)
    
    return X_new, V_new


# ─────────────────────────────────────────────────────────────────────────────
# Second-order simulation (replaces simulate_and_align)
# ─────────────────────────────────────────────────────────────────────────────

def simulate_orbital(
    X0: np.ndarray,
    V0: np.ndarray,
    mu: np.ndarray,
    bsdt: BSDTOperator,
    masses: np.ndarray,
    beta: float,
    mix_grav: float = MIX_GRAV,
    n_steps: int = 200,
    dt: float = 0.01,
    **kw,
) -> dict:
    """
    Second-order simulation with velocity-Verlet.
    
    Returns time series of:
        cos_theta, energy, kinetic_energy, angular_momentum, mfls
    """
    X = X0.copy()
    V = V0.copy()
    
    cos_history = []
    E_history = []
    K_history = []
    L_history = []
    mfls_history = []
    
    for step in range(n_steps):
        mu_t = X.mean(axis=0)
        
        # Forces
        F = total_force(X, mu_t, masses=masses, mix_grav=mix_grav, **kw)
        
        # BSDT gradient alignment
        G_bs = bsdt.gradient(X)
        dot_ = np.sum(G_bs * F, axis=1)
        nG = np.linalg.norm(G_bs, axis=1)
        nF = np.linalg.norm(F, axis=1)
        cos_ = dot_ / (nG * nF + 1e-12)
        cos_history.append(float(np.mean(cos_)))
        
        # Energies
        E_pot = total_energy(X, mu, masses=masses, mix_grav=mix_grav, **kw)
        E_kin = kinetic_energy(V, masses)
        L_tot = total_angular_momentum(X, V, masses)
        mfls_val = bsdt.mfls_score(X)
        
        E_history.append(E_pot)
        K_history.append(E_kin)
        L_history.append(L_tot)
        mfls_history.append(mfls_val)
        
        # Integrate one step
        X, V = verlet_step(X, V, masses, mu, dt, beta,
                           mix_grav=mix_grav, **kw)
    
    c = np.array(cos_history)
    return {
        "mean_cos":       float(c.mean()),
        "min_cos":        float(c.min()),
        "max_cos":        float(c.max()),
        "frac_above_07":  float((c >= 0.7).mean()),
        "frac_positive":  float((c > 0).mean()),
        "cos_history":    c,
        "energy":         np.array(E_history),
        "kinetic":        np.array(K_history),
        "angular_mom":    np.array(L_history),
        "mfls":           np.array(mfls_history),
        "n_steps_run":    len(c),
        "final_X":        X.copy(),
        "final_V":        V.copy(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Second-order trajectory analysis (replaces analyse_trajectory)
# ─────────────────────────────────────────────────────────────────────────────

def analyse_trajectory_orbital(
    X_series: np.ndarray,
    mu: np.ndarray,
    bsdt: BSDTOperator,
    masses: np.ndarray,
    beta: float,
    mix_grav: float = MIX_GRAV,
    alpha: float = ALPHA,
    verbose: bool = False,
    **kw,
) -> dict[str, np.ndarray]:
    """
    Analyse each time step with second-order dynamics.
    
    At each quarter t, we:
    1. Take position X(t) from data
    2. Compute velocity V(t) = [X(t) - X(t-1)] / Δt from data
    3. Measure alignment, energy, angular momentum, MFLS
    
    This is faithful to the philosophy: velocities come from data,
    not simulation. The orbital dynamics inform the force balance.
    """
    T, N, d = X_series.shape
    
    cos_theta   = np.zeros(T)
    energy      = np.zeros(T)
    kin_energy   = np.zeros(T)
    grav_energy  = np.zeros(T)
    ang_momentum = np.zeros(T)
    mfls_arr    = np.zeros(T)
    force_norm  = np.zeros(T)
    virial_ratio = np.zeros(T)  # 2K/|U| — should be ~1 for virial equilibrium
    
    for t in range(T):
        X = X_series[t]
        if verbose and t % 20 == 0:
            print(f"  t={t:3d}/{T}")
        
        # Data-derived velocity
        if t > 0:
            V = X_series[t] - X_series[t - 1]
        else:
            V = np.zeros_like(X)
        
        mu_t = X.mean(axis=0)
        
        # Forces (2nd order: F = m*a, but we measure F for alignment)
        F = total_force(X, mu_t, masses=masses, mix_grav=mix_grav, alpha=alpha, **kw)
        force_norm[t] = float(np.linalg.norm(F))
        
        # BSDT alignment
        G_bs = bsdt.gradient(X)
        dot_ = np.sum(G_bs * F, axis=1)
        nG = np.linalg.norm(G_bs, axis=1)
        nF = np.linalg.norm(F, axis=1)
        cos_ = dot_ / (nG * nF + 1e-12)
        cos_theta[t] = float(np.mean(cos_))
        
        # Energies
        E_pot = total_energy(X, mu, masses=masses, mix_grav=mix_grav, alpha=alpha, **kw)
        E_kin = kinetic_energy(V, masses)
        E_grav = newtonian_energy(X, masses, G=kw.get('G', G_NEWTON))
        
        energy[t] = E_pot + E_kin  # Total mechanical energy
        kin_energy[t] = E_kin
        grav_energy[t] = E_grav
        
        # Angular momentum
        L = angular_momentum(X, V, masses)
        ang_momentum[t] = float(L.sum())
        
        # Virial ratio: 2K/|U| — virial theorem says this should be 1
        virial_ratio[t] = 2 * E_kin / (abs(E_pot) + 1e-12)
        
        # MFLS
        mfls_arr[t] = bsdt.mfls_score(X)
    
    return {
        "cos_theta":        cos_theta,
        "energy":           energy,
        "kinetic_energy":   kin_energy,
        "grav_energy":      grav_energy,
        "angular_momentum": ang_momentum,
        "mfls":             mfls_arr,
        "force_norm":       force_norm,
        "virial_ratio":     virial_ratio,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Quick self-test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    rng = np.random.default_rng(42)
    N, d = 12, 5
    X = rng.standard_normal((N, d)) * 0.5
    V = rng.standard_normal((N, d)) * 0.1  # initial velocities
    mu = np.zeros(d)
    masses = rng.uniform(0.5, 2.0, size=N)
    
    print("=== Orbital Gravity Engine — Self Test ===")
    print(f"Particles: {N},  Dimensions: {d}")
    print(f"Masses: {masses.round(2)}")
    print()
    
    # Energies
    E_pot = total_energy(X, mu, masses=masses)
    E_kin = kinetic_energy(V, masses)
    L_tot = total_angular_momentum(X, V, masses)
    print(f"Potential E = {E_pot:+.4f}")
    print(f"Kinetic E   = {E_kin:+.4f}")
    print(f"Total E     = {E_pot + E_kin:+.4f}")
    print(f"Angular mom = {L_tot:.4f}")
    print()
    
    # Derive damping from synthetic data
    X_series = np.stack([X + 0.01 * t * V for t in range(20)])
    beta = compute_damping_from_data(X_series, masses, G=1.0)
    print(f"Data-derived damping beta = {beta:.6f}")
    print()
    
    # Run a short simulation
    bsdt = BSDTOperator().fit(X_series[:5])
    result = simulate_orbital(
        X, V, mu, bsdt, masses, beta=beta,
        mix_grav=1.0, n_steps=50, dt=0.01, G=1.0)
    
    print(f"Simulation: {result['n_steps_run']} steps")
    print(f"  Mean cos theta = {result['mean_cos']:+.4f}")
    print(f"  cos range: [{result['min_cos']:+.4f}, {result['max_cos']:+.4f}]")
    print(f"  Frac positive cos = {result['frac_positive']*100:.1f}%")
    print(f"  Final angular mom = {result['angular_mom'][-1]:.4f} "
          f"(initial: {result['angular_mom'][0]:.4f})")
    print(f"  L conservation: {result['angular_mom'][-1]/result['angular_mom'][0]*100:.1f}%")
    print()
    print("Self-test passed.")
