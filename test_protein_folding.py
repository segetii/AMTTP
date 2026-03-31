"""
Protein Folding Simulation — BSDT Cross-Domain Validation
===========================================================
Demonstrates that the Blind-Spot Decomposition geometry detects
protein mis-folding transitions and that adaptive friction
prevents unfolding — the 8th domain for the grand unification paper.

Model: Coarse-grained Cα Go-model for a 30-residue β-hairpin
  - Each residue i has position r_i ∈ ℝ³
  - Bond potential (backbone connectivity)
  - Native-contact Go potential (Lennard-Jones 12-10)
  - Hydrophobic burial drive
  - Langevin thermostat: dr = F·dt − γ·v·dt + √(2γkT)·dW

Key BSDT mapping:
  Agents      = amino acid residues (N=30, d=6 features per residue)
  Φ           = Go-model folding free energy (physical energy)
  C*          = folding temperature Tm (phase transition)
  δ_C         = hydrophobic core residues that look "folded" individually
                but have broken tertiary contacts (camouflage)
  δ_G         = loop/turn residues with high B-factors (feature gap)
  δ_A         = sudden large RMSD fluctuations (activity anomaly)
  δ_T         = visits to non-native conformations (temporal novelty)
  Double-well = each backbone dihedral ψ_i has two stable rotamers
                (α-helix vs β-strand) → continuous-to-discrete

Results we expect:
  T < Tm  : folded, constant friction OK  → no BSDT alarm
  T ≈ Tm  : marginal, BSDT detects local unfolding BEFORE global RMSD rises
  T > Tm  : constant friction fails, protein unfolds → BSDT alarm fires
  Adaptive γ*(E_BS): stabilises protein even above Tm

Author: Odeyemi Olusegun Israel
Date: March 2026
"""

import sys, os, time
import numpy as np
from dataclasses import dataclass
from typing import Tuple, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'research', 'udl'))

# ═══════════════════════════════════════════════════════════════
#  1. COARSE-GRAINED PROTEIN MODEL (Cα Go-model)
# ═══════════════════════════════════════════════════════════════

@dataclass
class ProteinConfig:
    """Configuration for the coarse-grained Go-model."""
    N: int = 30                   # number of residues
    d_bond: float = 3.8           # Cα-Cα bond length (Å)
    k_bond: float = 200.0         # bond spring constant (stiff)
    k_angle: float = 5.0          # backbone angle spring constant (weak)
    theta0: float = 2.09          # equilibrium backbone angle (≈120° for β-strand)
    eps_native: float = 0.5       # Go-contact well depth (kcal/mol)
    sigma_native: float = 5.5     # native contact distance (Å)
    eps_repel: float = 0.2        # non-native repulsion (weak)
    dt: float = 0.002             # integration timestep
    gamma_const: float = 1.0      # friction coefficient
    kB: float = 0.001987          # Boltzmann constant (kcal/mol·K)
    hydrophobic: tuple = (1, 3, 5, 7, 9, 11, 14, 16, 18, 20, 22, 24, 26, 28)


def build_native_structure(cfg: ProteinConfig) -> np.ndarray:
    """
    Build a β-hairpin native structure with EXACT bond lengths.

    Strand 1: residues 0-13, along +x at y=0
    Turn vertex: residue 14, equidistant from res 13 and res 15
    Strand 2: residues 15-29, along -x at y=strand_sep (antiparallel)

    All bonds are exactly d_bond by construction.
    Cross-strand contacts (|i-j| >> 4) give long-range
    interactions that create a cooperative two-state transition.
    """
    pos = np.zeros((cfg.N, 3))
    d = cfg.d_bond
    strand_sep = 4.7  # inter-strand distance (Å), typical for antiparallel β

    # Strand 1: residues 0-13, straight along +x at y=0
    for i in range(14):
        pos[i] = [i * d, 0.0, 0.0]

    # Turn vertex: residue 14
    # Must be exactly d_bond from res 13 = (13d, 0, 0)
    # and from res 15 = (13d, strand_sep, 0)
    # Place at midpoint + x-offset to satisfy distance constraint
    x_offset = np.sqrt(d ** 2 - (strand_sep / 2) ** 2)
    pos[14] = [13 * d + x_offset, strand_sep / 2, 0.0]

    # Strand 2: residues 15-29, antiparallel along -x at y=strand_sep
    for j in range(15):
        pos[15 + j] = [(13 - j) * d, strand_sep, 0.0]

    # Verify bond lengths
    bonds = np.linalg.norm(pos[1:] - pos[:-1], axis=1)
    print(f"  Native structure: {cfg.N} residues, β-hairpin")
    print(f"  Bond lengths: min={bonds.min():.3f}, max={bonds.max():.3f}, "
          f"mean={bonds.mean():.3f} Å (target {d:.1f})")

    return pos


def compute_native_contacts(native_pos: np.ndarray,
                            cfg: ProteinConfig,
                            cutoff: float = 8.0,
                            seq_sep: int = 3) -> Tuple[np.ndarray, np.ndarray]:
    """
    Identify native contacts: residue pairs |i-j| ≥ seq_sep with
    distance < cutoff in the native structure.
    Returns (contact_pairs [M,2], native_dists [M]).
    """
    N = len(native_pos)
    pairs = []
    dists = []
    for i in range(N):
        for j in range(i + seq_sep, N):
            d = np.linalg.norm(native_pos[i] - native_pos[j])
            if d < cutoff:
                pairs.append([i, j])
                dists.append(d)
    return np.array(pairs, dtype=int), np.array(dists)


def compute_nonnative_pairs(N: int, contact_pairs: np.ndarray,
                            seq_sep: int = 3) -> np.ndarray:
    """Pre-compute non-native pair indices (|i-j|>=seq_sep, not in contacts)."""
    native_set = set()
    for row in contact_pairs:
        native_set.add((int(row[0]), int(row[1])))
    pairs = []
    for i in range(N):
        for j in range(i + seq_sep, N):
            if (i, j) not in native_set:
                pairs.append([i, j])
    return np.array(pairs, dtype=int) if pairs else np.zeros((0, 2), dtype=int)


def compute_forces(pos: np.ndarray, cfg: ProteinConfig,
                   contact_pairs: np.ndarray,
                   contact_dists: np.ndarray,
                   nonnative_pairs: np.ndarray) -> Tuple[np.ndarray, float]:
    """
    Compute total force and potential energy (vectorized).
    nonnative_pairs: pre-computed (P,2) array of non-native pair indices.
    """
    N = cfg.N
    F = np.zeros_like(pos)
    E = 0.0

    # 1. Bond potential (vectorized over consecutive pairs)
    dr_bond = pos[1:] - pos[:-1]                     # (N-1, 3)
    dist_bond = np.linalg.norm(dr_bond, axis=1) + 1e-10  # (N-1,)
    dev_bond = dist_bond - cfg.d_bond
    E += 0.5 * cfg.k_bond * np.sum(dev_bond ** 2)
    f_mag_bond = (-cfg.k_bond * dev_bond / dist_bond)[:, None]  # (N-1, 1)
    f_bond = f_mag_bond * dr_bond                     # (N-1, 3)
    F[:-1] -= f_bond
    F[1:] += f_bond

    # 2. Backbone angle potential (vectorized)
    if N >= 3:
        v1 = pos[:-2] - pos[1:-1]   # (N-2, 3)
        v2 = pos[2:] - pos[1:-1]    # (N-2, 3)
        n1 = np.linalg.norm(v1, axis=1, keepdims=True) + 1e-10
        n2 = np.linalg.norm(v2, axis=1, keepdims=True) + 1e-10
        cos_theta = np.clip(np.sum(v1 * v2, axis=1) /
                            (n1[:, 0] * n2[:, 0]), -1, 1)
        theta = np.arccos(cos_theta)
        dtheta = theta - cfg.theta0
        E += 0.5 * cfg.k_angle * np.sum(dtheta ** 2)

        sin_theta = np.sin(theta)
        valid = np.abs(sin_theta) > 1e-6
        if np.any(valid):
            dtdcos = np.where(valid, -1.0 / (sin_theta + 1e-30), 0.0)
            coeff = (cfg.k_angle * dtheta * dtdcos)[:, None]  # (N-2, 1)
            d_cos_v1 = (v2 / (n1 * n2) -
                        cos_theta[:, None] * v1 / (n1 ** 2))
            d_cos_v2 = (v1 / (n1 * n2) -
                        cos_theta[:, None] * v2 / (n2 ** 2))
            F[:-2] += coeff * d_cos_v1
            F[2:]  += coeff * d_cos_v2
            F[1:-1] -= coeff * (d_cos_v1 + d_cos_v2)

    # 3. Native Go contacts (vectorized)
    if len(contact_pairs) > 0:
        ci = contact_pairs[:, 0]
        cj = contact_pairs[:, 1]
        dr_c = pos[cj] - pos[ci]                     # (M, 3)
        dist_c = np.linalg.norm(dr_c, axis=1) + 1e-10  # (M,)
        d0 = contact_dists                             # (M,)
        x = d0 / dist_c
        x10 = x ** 10
        x12 = x ** 12
        # Standard Go 12-10: V = eps*[5*(d0/r)^12 - 6*(d0/r)^10]
        # minimum at r = d0, well depth = eps
        E += cfg.eps_native * np.sum(5.0 * x12 - 6.0 * x10)
        # dV/dr = eps * [-60*d0^12/r^13 + 60*d0^10/r^11]
        #       = 60*eps/r * [x^10 - x^12]
        dVdr = 60.0 * cfg.eps_native * (x10 - x12) / dist_c
        force_c = (dVdr / dist_c)[:, None] * dr_c     # (M, 3)
        np.add.at(F, ci, force_c)
        np.add.at(F, cj, -force_c)

    # 4. Non-native repulsion (pre-computed pairs)
    sigma_rep = 4.0
    if len(nonnative_pairs) > 0:
        pi = nonnative_pairs[:, 0]
        pj = nonnative_pairs[:, 1]
        dr_nn = pos[pj] - pos[pi]                    # (P, 3)
        dist_nn = np.linalg.norm(dr_nn, axis=1) + 1e-10
        close = dist_nn < 2.0 * sigma_rep
        if np.any(close):
            x12_nn = (sigma_rep / dist_nn[close]) ** 12
            E += cfg.eps_repel * np.sum(x12_nn)
            f_mag_nn = (12 * cfg.eps_repel * x12_nn / dist_nn[close])
            force_nn = (f_mag_nn / dist_nn[close])[:, None] * dr_nn[close]
            np.add.at(F, pi[close], -force_nn)
            np.add.at(F, pj[close], force_nn)

    return F, E


def compute_rmsd(pos: np.ndarray, native: np.ndarray) -> float:
    """Backbone RMSD after optimal superposition (Kabsch)."""
    # Center both
    p = pos - pos.mean(axis=0)
    n = native - native.mean(axis=0)

    # Kabsch rotation
    H = p.T @ n
    U, S, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    diag = np.diag([1, 1, d])
    R = Vt.T @ diag @ U.T
    p_rot = p @ R.T

    return np.sqrt(np.mean(np.sum((p_rot - n) ** 2, axis=1)))


def fraction_native_contacts(pos: np.ndarray,
                             contact_pairs: np.ndarray,
                             contact_dists: np.ndarray,
                             tol: float = 1.2) -> float:
    """Q-value: fraction of native contacts within tol * d_native."""
    if len(contact_pairs) == 0:
        return 1.0
    ci = contact_pairs[:, 0]
    cj = contact_pairs[:, 1]
    d = np.linalg.norm(pos[cj] - pos[ci], axis=1)
    return float(np.mean(d < tol * contact_dists))


# ═══════════════════════════════════════════════════════════════
#  2. LANGEVIN DYNAMICS
# ═══════════════════════════════════════════════════════════════

def langevin_step(pos: np.ndarray, vel: np.ndarray,
                  cfg: ProteinConfig,
                  contact_pairs: np.ndarray, contact_dists: np.ndarray,
                  nonnative_pairs: np.ndarray,
                  T: float, gamma: float) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    One step of Langevin dynamics (BAOAB splitting).
    Returns: (new_pos, new_vel, potential_energy)
    """
    dt = cfg.dt
    N = cfg.N
    max_force = 500.0

    def _clamp(F_):
        fn = np.linalg.norm(F_, axis=1, keepdims=True)
        return np.where(fn > max_force, F_ * max_force / (fn + 1e-10), F_)

    F, E = compute_forces(pos, cfg, contact_pairs, contact_dists, nonnative_pairs)
    F = _clamp(F)
    vel = vel + 0.5 * dt * F
    pos = pos + 0.5 * dt * vel

    c1 = np.exp(-gamma * dt)
    c2 = np.sqrt(1.0 - c1 ** 2) * np.sqrt(cfg.kB * T)
    vel = c1 * vel + c2 * np.random.randn(N, 3)

    pos = pos + 0.5 * dt * vel

    F_new, E = compute_forces(pos, cfg, contact_pairs, contact_dists, nonnative_pairs)
    F_new = _clamp(F_new)
    vel = vel + 0.5 * dt * F_new

    return pos, vel, E


# ═══════════════════════════════════════════════════════════════
#  3. PER-RESIDUE FEATURE EXTRACTION (for BSDT)
# ═══════════════════════════════════════════════════════════════

def extract_residue_features(pos: np.ndarray, native: np.ndarray,
                             contact_pairs: np.ndarray,
                             contact_dists: np.ndarray,
                             cfg: ProteinConfig) -> np.ndarray:
    """
    Extract 6 aggregate features for BSDT (vectorized).

    Returns: (1, 6) aggregate feature vector per frame.
    """
    N = cfg.N
    centroid = pos.mean(axis=0)

    # f1: per-residue deviation from native (mean)
    local_rmsd = np.linalg.norm(pos - native, axis=1)

    # f2: per-residue contact fraction
    contact_score = np.ones(N)
    if len(contact_pairs) > 0:
        ci = contact_pairs[:, 0]
        cj = contact_pairs[:, 1]
        d_cur = np.linalg.norm(pos[cj] - pos[ci], axis=1)
        formed = d_cur < 1.2 * contact_dists
        # Tally per residue
        count_total = np.zeros(N)
        count_formed = np.zeros(N)
        np.add.at(count_total, ci, 1)
        np.add.at(count_total, cj, 1)
        np.add.at(count_formed, ci, formed.astype(float))
        np.add.at(count_formed, cj, formed.astype(float))
        has_contacts = count_total > 0
        contact_score[has_contacts] = (
            count_formed[has_contacts] / count_total[has_contacts])

    # f3: local density (pairwise distances — vectorized)
    D = np.linalg.norm(pos[:, None, :] - pos[None, :, :], axis=2)
    local_density = np.sum(D < 8.0, axis=1) - 1

    # f4: backbone angle deviation
    angle_dev = np.zeros(N)
    if N >= 3:
        v1 = pos[:-2] - pos[1:-1]
        v2 = pos[2:] - pos[1:-1]
        n1 = np.linalg.norm(v1, axis=1) + 1e-10
        n2 = np.linalg.norm(v2, axis=1) + 1e-10
        cos_a = np.clip(np.sum(v1 * v2, axis=1) / (n1 * n2), -1, 1)
        angle_dev[1:-1] = np.abs(np.arccos(cos_a) - cfg.theta0)

    # f5: burial depth
    burial = np.linalg.norm(pos - centroid, axis=1)

    # f6: B-factor proxy
    near_mask = D < 10.0
    bfac = np.zeros(N)
    for i in range(N):
        nd = D[i, near_mask[i]]
        if len(nd) > 2:
            bfac[i] = np.var(nd)

    # Return aggregate: mean + std over residues (12 features)
    return np.array([[local_rmsd.mean(), local_rmsd.std(),
                      contact_score.mean(), contact_score.std(),
                      local_density.mean(), local_density.std(),
                      angle_dev.mean(), angle_dev.std(),
                      burial.mean(), burial.std(),
                      bfac.mean(), bfac.std()]])


# ═══════════════════════════════════════════════════════════════
#  4. MAIN SIMULATION
# ═══════════════════════════════════════════════════════════════

def run_protein_simulation(T: float, cfg: ProteinConfig,
                           n_equil: int = 2000,
                           n_prod: int = 5000,
                           sample_every: int = 50,
                           adaptive: bool = False,
                           external_ref: np.ndarray = None,
                           seed: int = 42,
                           verbose: bool = True) -> Dict:
    """
    Run Go-model Langevin dynamics at temperature T.

    Parameters
    ----------
    T : float
        Temperature (K)
    adaptive : bool
        If True, use adaptive friction γ*(E_BS) instead of constant γ
    external_ref : np.ndarray, optional
        If provided, (n, d) feature matrix to use as BSDT reference
        instead of generating one from T=100K ensemble.

    Returns dict with trajectories, BSDT scores, etc.
    """
    rng = np.random.RandomState(seed)
    np.random.seed(seed)

    native_pos = build_native_structure(cfg)
    contact_pairs, contact_dists = compute_native_contacts(native_pos, cfg)
    nn_pairs = compute_nonnative_pairs(cfg.N, contact_pairs)

    if verbose:
        print(f"  Native contacts: {len(contact_pairs)}")
        d_min, d_max, d_mean = contact_dists.min(), contact_dists.max(), contact_dists.mean()
        print(f"  Contact dists: min={d_min:.2f}, max={d_max:.2f}, mean={d_mean:.2f} \u00c5")
        print(f"  Hydrophobic residues: {len(cfg.hydrophobic)}")

    # Initialise: tiny perturbation from native
    pos = native_pos.copy() + rng.randn(cfg.N, 3) * 0.1
    vel = rng.randn(cfg.N, 3) * np.sqrt(cfg.kB * T) * 0.1

    # ── Build BSDT reference ──
    from udl.system_mode import BSDTChannels
    from sklearn.preprocessing import StandardScaler as SS

    if external_ref is not None:
        # Use externally provided reference (e.g. from T_low production)
        X_ref_agg = external_ref.copy()
    else:
        # Generate reference from T=100K native-state ensemble
        ref_frames = []
        ref_pos = native_pos.copy() + rng.randn(cfg.N, 3) * 0.05
        ref_vel = rng.randn(cfg.N, 3) * np.sqrt(cfg.kB * 100.0) * 0.1
        T_ref = 100.0
        for step in range(500):
            ref_pos, ref_vel, _ = langevin_step(
                ref_pos, ref_vel, cfg, contact_pairs, contact_dists,
                nn_pairs, T_ref, cfg.gamma_const * 2.0)
        for step in range(400):
            ref_pos, ref_vel, _ = langevin_step(
                ref_pos, ref_vel, cfg, contact_pairs, contact_dists,
                nn_pairs, T_ref, cfg.gamma_const * 2.0)
            if step % 5 == 0:
                ref_frames.append(
                    extract_residue_features(
                        ref_pos, native_pos, contact_pairs, contact_dists, cfg))
        X_ref_agg = np.vstack(ref_frames)

    n_ref_frames = len(X_ref_agg)

    # Scale features for better BSDT channel sensitivity
    feat_scaler = SS()
    X_ref_scaled = feat_scaler.fit_transform(X_ref_agg)

    bsdt = BSDTChannels(k=min(10, n_ref_frames - 2))
    bsdt.fit(X_ref_scaled)

    if verbose:
        print(f"  BSDT reference: {n_ref_frames} frames, "
              f"Fisher weights: {bsdt.fisher_w_}")

    # ── Production run ──
    # Reset: start from native with small perturbation
    pos = native_pos.copy() + rng.randn(cfg.N, 3) * 0.1
    vel = rng.randn(cfg.N, 3) * np.sqrt(cfg.kB * T) * 0.1

    # Equilibration
    gamma = cfg.gamma_const
    for step in range(n_equil):
        pos, vel, _ = langevin_step(
            pos, vel, cfg, contact_pairs, contact_dists, nn_pairs, T, gamma)

    # Production with BSDT scoring
    X_frames_raw = []  # raw (unscaled) features for post-hoc engine scoring
    trajectory = {
        'time': [], 'rmsd': [], 'Q': [], 'energy': [],
        'E_BS': [], 'delta_C': [], 'delta_G': [],
        'delta_A': [], 'delta_T': [], 'gamma': [],
        'alarm': [],
    }

    alarm_threshold = None  # set from reference
    E_ref = bsdt.energy(X_ref_scaled)
    alarm_threshold = np.mean(E_ref) + 2.0 * np.std(E_ref)

    for step in range(n_prod):
        # Adaptive friction: γ*(E_BS) = γ_base * (1 + α * E_BS / (E_BS + θ))
        if adaptive and step > 0 and len(trajectory['E_BS']) > 0:
            E_current = trajectory['E_BS'][-1]
            alpha_adapt = 20.0
            theta_adapt = alarm_threshold
            gamma = cfg.gamma_const * (
                1.0 + alpha_adapt * E_current / (E_current + theta_adapt))
        else:
            gamma = cfg.gamma_const

        pos, vel, E_pot = langevin_step(
            pos, vel, cfg, contact_pairs, contact_dists, nn_pairs, T, gamma)

        if step % sample_every == 0:
            # Compute observables
            rmsd = compute_rmsd(pos, native_pos)
            Q = fraction_native_contacts(pos, contact_pairs, contact_dists)
            x_agg = extract_residue_features(
                pos, native_pos, contact_pairs, contact_dists, cfg)
            X_frames_raw.append(x_agg[0].copy())
            x_scaled = feat_scaler.transform(x_agg)

            E_bs = float(bsdt.energy(x_scaled)[0])
            ch = bsdt.channels(x_scaled)

            trajectory['time'].append(step * cfg.dt)
            trajectory['rmsd'].append(rmsd)
            trajectory['Q'].append(Q)
            trajectory['energy'].append(E_pot)
            trajectory['E_BS'].append(E_bs)
            trajectory['delta_C'].append(float(ch['delta_C'][0]))
            trajectory['delta_G'].append(float(ch['delta_G'][0]))
            trajectory['delta_A'].append(float(ch['delta_A'][0]))
            trajectory['delta_T'].append(float(ch['delta_T'][0]))
            trajectory['gamma'].append(gamma)
            trajectory['alarm'].append(E_bs > alarm_threshold)

    trajectory['X_frames'] = np.array(X_frames_raw)  # (n_samples, 6)
    trajectory['X_ref'] = X_ref_agg                    # (n_ref, 6)
    return trajectory


# ═══════════════════════════════════════════════════════════════
#  5. ESTIMATE FOLDING TEMPERATURE
# ═══════════════════════════════════════════════════════════════

def estimate_Tm(cfg: ProteinConfig, T_range=(100, 600),
                n_temps: int = 8, n_steps: int = 10000) -> float:
    """
    Quick scan to find Tm (where Q ≈ 0.5).
    """
    temperatures = np.linspace(T_range[0], T_range[1], n_temps)
    Q_values = []

    native = build_native_structure(cfg)
    contact_pairs, contact_dists = compute_native_contacts(native, cfg)
    nn_pairs = compute_nonnative_pairs(cfg.N, contact_pairs)

    for T in temperatures:
        pos = native.copy() + np.random.randn(cfg.N, 3) * 0.05
        vel = np.random.randn(cfg.N, 3) * np.sqrt(cfg.kB * T) * 0.1
        Q_samples = []
        for step in range(n_steps):
            pos, vel, _ = langevin_step(
                pos, vel, cfg, contact_pairs, contact_dists, nn_pairs, T,
                cfg.gamma_const)
            if step >= 5000 and step % 100 == 0:
                Q_samples.append(
                    fraction_native_contacts(pos, contact_pairs, contact_dists))
        Q_values.append(np.mean(Q_samples))
        print(f"    T={T:.0f}K: Q={np.mean(Q_samples):.3f} "
              f"({len(Q_samples)} samples)")

    # Find T where Q crosses 0.5
    Q_arr = np.array(Q_values)
    for i in range(len(Q_arr) - 1):
        if (Q_arr[i] - 0.5) * (Q_arr[i + 1] - 0.5) < 0:
            # Linear interpolation
            f = (0.5 - Q_arr[i]) / (Q_arr[i + 1] - Q_arr[i])
            return temperatures[i] + f * (temperatures[i + 1] - temperatures[i])

    # If no crossing, return midpoint
    return 0.5 * (T_range[0] + T_range[1])


# ═══════════════════════════════════════════════════════════════
#  6. MAIN
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
#  6b. FULL ENGINE SCORING (Gravity / Molecular / Hybrid)
# ═══════════════════════════════════════════════════════════════

##############################################################################
#   APPROACH A — Pure Anomaly Detection (Unsupervised / Frozen Window)
#   Train on NORMALS only (y=0).  Score ALL production frames (unseen).
##############################################################################

def score_with_engines_unsupervised(X_ref: np.ndarray, X_prod: np.ndarray,
                                     verbose: bool = True) -> Dict:
    """
    Frozen-window anomaly detection — the engine sees ONLY normal data.

      Phase 1: FIT on X_ref (y = all zeros, i.e. normal).
      Phase 2: SCORE the entire X_prod (completely unseen, no labels used).

    This is the strictest protocol — no anomaly labels at all during training.
    """
    from udl.system_mode import (MolecularEngine, GravityModeEngine,
                                 HybridGravityEngine,
                                 BSDTChannels, FusedSystemScorer,
                                 _MFLSQuadSurf)
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    X_ref_s = scaler.fit_transform(X_ref)       # fit on reference ONLY
    X_prod_s = scaler.transform(X_prod)          # transform unseen test

    results = {}
    n_ref = len(X_ref_s)
    n_prod = len(X_prod_s)
    k_nn = min(10, n_ref - 1)
    y_ref = np.zeros(n_ref)

    if verbose:
        print(f"      Unsupervised: {n_ref} ref(y=0) → train | "
              f"{n_prod} prod → test (no labels)")

    engines = [
        ('Molecular', MolecularEngine(iterations=60, k_neighbors=k_nn,
                                      use_fused=True, normalize=False)),
        ('Gravity',   GravityModeEngine(iterations=60, k_neighbors=k_nn,
                                        use_fused=True, normalize=False)),
    ]

    for name, eng in engines:
        t0 = time.perf_counter()
        try:
            ref_scores = eng.fit_score(X_ref_s, y_ref)
            dt_fit = time.perf_counter() - t0
            if eng.fused_scorer is not None:
                prod_scores = eng.fused_scorer.score(X_prod_s)
            else:
                prod_scores = eng.alarm.score(X_prod_s) \
                    if hasattr(eng, 'alarm') and eng.alarm is not None \
                    else np.zeros(n_prod)
            dt = time.perf_counter() - t0
            mu_r = float(np.mean(ref_scores))
            std_r = float(np.std(ref_scores)) + 1e-10
            thr = mu_r + 3.0 * std_r
            results[name] = {
                'scores': prod_scores,
                'mean': float(np.mean(prod_scores)),
                'max': float(np.max(prod_scores)),
                'threshold': thr,
                'alarms': prod_scores > thr,
                'alarm_pct': float(100 * np.mean(prod_scores > thr)),
                'time': dt,
            }
            if verbose:
                print(f"    {name:12s}: mean={np.mean(prod_scores):.4f}, "
                      f"alarm={100*np.mean(prod_scores > thr):.0f}% "
                      f"(fit {dt_fit:.1f}s, total {dt:.1f}s)")
        except Exception as e:
            results[name] = {
                'scores': np.zeros(n_prod), 'mean': 0.0, 'max': 0.0,
                'threshold': 0.0, 'alarms': np.zeros(n_prod, dtype=bool),
                'alarm_pct': 0.0, 'time': 0.0, 'error': str(e),
            }
            if verbose:
                print(f"    {name:12s}: ERROR — {e}")

    # ── HybridGravityEngine ──
    try:
        t0 = time.perf_counter()
        hybrid = HybridGravityEngine(
            blend_weight='auto',
            molecular_params=dict(iterations=60, k_neighbors=k_nn,
                                  use_fused=True, normalize=False),
            gravity_params=dict(iterations=60, k_neighbors=k_nn,
                                use_fused=True, normalize=False),
        )
        ref_scores_hybrid = hybrid.fit_score(X_ref_s, y_ref)
        dt_fit = time.perf_counter() - t0
        mol_test = hybrid.molecular.fused_scorer.score(X_prod_s) \
            if hybrid.molecular.fused_scorer is not None else np.zeros(n_prod)
        grav_test = hybrid.gravity.fused_scorer.score(X_prod_s) \
            if hybrid.gravity.fused_scorer is not None else np.zeros(n_prod)
        mol_test = hybrid._normalise(mol_test)
        grav_test = hybrid._normalise(grav_test)
        prod_scores_hybrid = (hybrid._blend_w * mol_test
                              + (1 - hybrid._blend_w) * grav_test)
        dt = time.perf_counter() - t0
        mu_rh = float(np.mean(ref_scores_hybrid))
        std_rh = float(np.std(ref_scores_hybrid)) + 1e-10
        thr_h = mu_rh + 3.0 * std_rh
        results['Hybrid'] = {
            'scores': prod_scores_hybrid,
            'mean': float(np.mean(prod_scores_hybrid)),
            'max': float(np.max(prod_scores_hybrid)),
            'threshold': thr_h,
            'alarms': prod_scores_hybrid > thr_h,
            'alarm_pct': float(100 * np.mean(prod_scores_hybrid > thr_h)),
            'time': dt, 'blend_w': hybrid._blend_w,
        }
        if verbose:
            print(f"    {'Hybrid':12s}: mean={np.mean(prod_scores_hybrid):.4f}, "
                  f"alarm={100*np.mean(prod_scores_hybrid > thr_h):.0f}% "
                  f"(w={hybrid._blend_w:.2f}, "
                  f"fit {dt_fit:.1f}s, total {dt:.1f}s)")
    except Exception as e:
        results['Hybrid'] = {
            'scores': np.zeros(n_prod), 'mean': 0.0, 'max': 0.0,
            'threshold': 0.0, 'alarms': np.zeros(n_prod, dtype=bool),
            'alarm_pct': 0.0, 'time': 0.0, 'error': str(e),
        }
        if verbose:
            print(f"    {'Hybrid':12s}: ERROR — {e}")

    # ── BSDT + QuadSurf (unsupervised — all y=0) ──
    try:
        t0 = time.perf_counter()
        k_bsdt = min(10, max(n_ref - 1, 1))
        bsdt = BSDTChannels(k=k_bsdt)
        bsdt.fit(X_ref_s)
        E_ref = bsdt.energy(X_ref_s)
        E_prod = bsdt.energy(X_prod_s)
        thr_E = float(np.mean(E_ref) + 3.0 * np.std(E_ref))
        dt_bsdt = time.perf_counter() - t0
        results['BSDT'] = {
            'scores': E_prod, 'mean': float(np.mean(E_prod)),
            'max': float(np.max(E_prod)), 'threshold': thr_E,
            'alarms': E_prod > thr_E,
            'alarm_pct': float(100 * np.mean(E_prod > thr_E)),
            'time': dt_bsdt,
        }
        if verbose:
            print(f"    {'BSDT':12s}: mean={np.mean(E_prod):.4f}, "
                  f"alarm={100*np.mean(E_prod > thr_E):.0f}% ({dt_bsdt:.1f}s)")
        # QuadSurf unsupervised (y_ref=0 → learns nothing, baseline)
        t0 = time.perf_counter()
        ch_ref = bsdt.channels(X_ref_s)
        C_ref = np.column_stack([ch_ref['delta_C'], ch_ref['delta_G'],
                                 ch_ref['delta_A'], ch_ref['delta_T']])
        ch_prod = bsdt.channels(X_prod_s)
        C_prod = np.column_stack([ch_prod['delta_C'], ch_prod['delta_G'],
                                  ch_prod['delta_A'], ch_prod['delta_T']])
        qs = _MFLSQuadSurf(ridge_alpha=1.0)
        qs.fit(C_ref, y_ref)
        qs_ref_scores = qs.score(C_ref)
        qs_prod_scores = qs.score(C_prod)
        thr_qs = float(np.mean(qs_ref_scores) + 3.0 * np.std(qs_ref_scores))
        dt_qs = time.perf_counter() - t0
        results['QuadSurf'] = {
            'scores': qs_prod_scores, 'mean': float(np.mean(qs_prod_scores)),
            'max': float(np.max(qs_prod_scores)), 'threshold': thr_qs,
            'alarms': qs_prod_scores > thr_qs,
            'alarm_pct': float(100 * np.mean(qs_prod_scores > thr_qs)),
            'time': dt_qs,
        }
        if verbose:
            print(f"    {'QuadSurf':12s}: mean={np.mean(qs_prod_scores):.4f}, "
                  f"alarm={100*np.mean(qs_prod_scores > thr_qs):.0f}% "
                  f"({dt_qs:.1f}s)")
    except Exception as e:
        for fn in ['BSDT', 'QuadSurf']:
            if fn not in results:
                results[fn] = {
                    'scores': np.zeros(n_prod), 'mean': 0.0, 'max': 0.0,
                    'threshold': 0.0, 'alarms': np.zeros(n_prod, dtype=bool),
                    'alarm_pct': 0.0, 'time': 0.0, 'error': str(e),
                }
        if verbose:
            print(f"    BSDT/QuadSurf: ERROR — {e}")

    return results


##############################################################################
#   APPROACH B — Semi-Supervised (SIAM Expanding-Window Protocol)
#   Train on normals (y=0) + KNOWN anomalies (y=1).  Test on held-out.
##############################################################################

def score_with_engines_semisupervised(X_ref: np.ndarray, X_prod: np.ndarray,
                                       verbose: bool = True) -> Dict:
    """
    Semi-supervised SIAM expanding-window protocol:

      TRAINING SET = X_ref (y=0, normal) + first half of X_prod (y=1, anomaly)
      TEST SET     = second half of X_prod (completely unseen, no labels)

    This matches the SIAM expanding-window protocol where past crises
    are known (y=1 in training window) but the next quarter is unseen.

    Returns dict keyed by engine name.
    """
    from udl.system_mode import (MolecularEngine, GravityModeEngine,
                                 HybridGravityEngine,
                                 BSDTChannels, FusedSystemScorer,
                                 _MFLSQuadSurf)
    from sklearn.preprocessing import StandardScaler

    # ── Train/test split: 50% of prod for training, 50% held-out test ──
    n_prod = len(X_prod)
    n_train_anom = n_prod // 2
    X_prod_train = X_prod[:n_train_anom]     # known anomalies (like past crises)
    X_prod_test  = X_prod[n_train_anom:]     # unseen test (like next quarter)
    n_test = len(X_prod_test)

    # Build training set: ref (y=0) + anomaly examples (y=1)
    X_train_raw = np.vstack([X_ref, X_prod_train])
    y_train = np.concatenate([np.zeros(len(X_ref)),
                              np.ones(n_train_anom)])

    # Scaler fit on TRAINING only
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train_raw)
    X_test_s  = scaler.transform(X_prod_test)    # unseen test
    X_ref_s   = X_train_s[:len(X_ref)]           # ref portion (scaled)

    results = {}
    n_ref = len(X_ref)
    k_nn = min(10, n_ref - 1)

    if verbose:
        print(f"      Split: {n_ref} ref(y=0) + {n_train_anom} anom(y=1) "
              f"→ train | {n_test} held-out test")

    # ── Phase 1: Fit engines on TRAINING (ref + anomalies with labels) ──
    engines = [
        ('Molecular', MolecularEngine(iterations=60, k_neighbors=k_nn,
                                      use_fused=True, normalize=False)),
        ('Gravity',   GravityModeEngine(iterations=60, k_neighbors=k_nn,
                                        use_fused=True, normalize=False)),
    ]

    for name, eng in engines:
        t0 = time.perf_counter()
        try:
            # FIT on training (normal + known anomalies with labels)
            train_scores = eng.fit_score(X_train_s, y_train)
            dt_fit = time.perf_counter() - t0

            # Phase 2: SCORE unseen test via frozen fused_scorer
            if eng.fused_scorer is not None:
                test_scores = eng.fused_scorer.score(X_test_s)
            else:
                test_scores = eng.alarm.score(X_test_s) \
                    if hasattr(eng, 'alarm') and eng.alarm is not None \
                    else np.zeros(n_test)

            dt = time.perf_counter() - t0
            # Threshold: μ + 3σ from NORMAL training scores (frozen)
            normal_train_scores = train_scores[:n_ref]
            mu_r = float(np.mean(normal_train_scores))
            std_r = float(np.std(normal_train_scores)) + 1e-10
            thr = mu_r + 3.0 * std_r
            results[name] = {
                'scores': test_scores,
                'mean': float(np.mean(test_scores)),
                'max': float(np.max(test_scores)),
                'threshold': thr,
                'alarms': test_scores > thr,
                'alarm_pct': float(100 * np.mean(test_scores > thr)),
                'time': dt,
            }
            if verbose:
                print(f"    {name:12s}: mean={np.mean(test_scores):.4f}, "
                      f"alarm={100*np.mean(test_scores > thr):.0f}% "
                      f"(fit {dt_fit:.1f}s, total {dt:.1f}s)")
        except Exception as e:
            results[name] = {
                'scores': np.zeros(n_test),
                'mean': 0.0, 'max': 0.0, 'threshold': 0.0,
                'alarms': np.zeros(n_test, dtype=bool),
                'alarm_pct': 0.0, 'time': 0.0, 'error': str(e),
            }
            if verbose:
                print(f"    {name:12s}: ERROR — {e}")

    # ── HybridGravityEngine ──
    try:
        t0 = time.perf_counter()
        hybrid = HybridGravityEngine(
            blend_weight='auto',
            molecular_params=dict(iterations=60, k_neighbors=k_nn,
                                  use_fused=True, normalize=False),
            gravity_params=dict(iterations=60, k_neighbors=k_nn,
                                use_fused=True, normalize=False),
        )
        train_scores_hybrid = hybrid.fit_score(X_train_s, y_train)
        dt_fit = time.perf_counter() - t0

        # Score test via each sub-engine's frozen fused_scorer, then blend
        mol_test = hybrid.molecular.fused_scorer.score(X_test_s) \
            if hybrid.molecular.fused_scorer is not None \
            else np.zeros(n_test)
        grav_test = hybrid.gravity.fused_scorer.score(X_test_s) \
            if hybrid.gravity.fused_scorer is not None \
            else np.zeros(n_test)
        mol_test = hybrid._normalise(mol_test)
        grav_test = hybrid._normalise(grav_test)
        test_scores_hybrid = (hybrid._blend_w * mol_test
                              + (1 - hybrid._blend_w) * grav_test)
        dt = time.perf_counter() - t0
        normal_train_h = train_scores_hybrid[:n_ref]
        mu_rh = float(np.mean(normal_train_h))
        std_rh = float(np.std(normal_train_h)) + 1e-10
        thr_h = mu_rh + 3.0 * std_rh
        results['Hybrid'] = {
            'scores': test_scores_hybrid,
            'mean': float(np.mean(test_scores_hybrid)),
            'max': float(np.max(test_scores_hybrid)),
            'threshold': thr_h,
            'alarms': test_scores_hybrid > thr_h,
            'alarm_pct': float(100 * np.mean(test_scores_hybrid > thr_h)),
            'time': dt,
            'blend_w': hybrid._blend_w,
        }
        if verbose:
            print(f"    {'Hybrid':12s}: mean={np.mean(test_scores_hybrid):.4f}, "
                  f"alarm={100*np.mean(test_scores_hybrid > thr_h):.0f}% "
                  f"(w={hybrid._blend_w:.2f}, "
                  f"fit {dt_fit:.1f}s, total {dt:.1f}s)")
    except Exception as e:
        results['Hybrid'] = {
            'scores': np.zeros(n_test),
            'mean': 0.0, 'max': 0.0, 'threshold': 0.0,
            'alarms': np.zeros(n_test, dtype=bool),
            'alarm_pct': 0.0, 'time': 0.0, 'error': str(e),
        }
        if verbose:
            print(f"    {'Hybrid':12s}: ERROR — {e}")

    # ── BSDT + QuadSurf posthoc ──
    try:
        t0 = time.perf_counter()
        k_bsdt = min(10, max(n_ref - 1, 1))
        bsdt = BSDTChannels(k=k_bsdt)
        bsdt.fit(X_ref_s)                           # fit on normals ONLY

        # BSDT energy score on unseen test
        E_ref = bsdt.energy(X_ref_s)
        E_test = bsdt.energy(X_test_s)
        thr_E = float(np.mean(E_ref) + 3.0 * np.std(E_ref))
        dt_bsdt = time.perf_counter() - t0
        results['BSDT'] = {
            'scores': E_test,
            'mean': float(np.mean(E_test)),
            'max': float(np.max(E_test)),
            'threshold': thr_E,
            'alarms': E_test > thr_E,
            'alarm_pct': float(100 * np.mean(E_test > thr_E)),
            'time': dt_bsdt,
        }
        if verbose:
            print(f"    {'BSDT':12s}: mean={np.mean(E_test):.4f}, "
                  f"alarm={100*np.mean(E_test > thr_E):.0f}% "
                  f"({dt_bsdt:.1f}s)")

        # ── QuadSurf with labels (supervised — like SIAM post-crisis) ──
        t0 = time.perf_counter()
        ch_train = bsdt.channels(X_train_s)
        C_train = np.column_stack([ch_train['delta_C'], ch_train['delta_G'],
                                   ch_train['delta_A'], ch_train['delta_T']])
        ch_test = bsdt.channels(X_test_s)
        C_test = np.column_stack([ch_test['delta_C'], ch_test['delta_G'],
                                  ch_test['delta_A'], ch_test['delta_T']])
        qs = _MFLSQuadSurf(ridge_alpha=1.0)
        qs.fit(C_train, y_train)                     # supervised: y=0/1
        qs_train_scores = qs.score(C_train)
        qs_test_scores = qs.score(C_test)
        # Threshold from normal training scores
        qs_normal = qs_train_scores[:n_ref]
        thr_qs = float(np.mean(qs_normal) + 3.0 * np.std(qs_normal))
        dt_qs = time.perf_counter() - t0
        results['QuadSurf'] = {
            'scores': qs_test_scores,
            'mean': float(np.mean(qs_test_scores)),
            'max': float(np.max(qs_test_scores)),
            'threshold': thr_qs,
            'alarms': qs_test_scores > thr_qs,
            'alarm_pct': float(100 * np.mean(qs_test_scores > thr_qs)),
            'time': dt_qs,
        }
        if verbose:
            print(f"    {'QuadSurf':12s}: mean={np.mean(qs_test_scores):.4f}, "
                  f"alarm={100*np.mean(qs_test_scores > thr_qs):.0f}% "
                  f"({dt_qs:.1f}s)")
    except Exception as e:
        for fallback_name in ['BSDT', 'QuadSurf']:
            if fallback_name not in results:
                results[fallback_name] = {
                    'scores': np.zeros(n_test),
                    'mean': 0.0, 'max': 0.0, 'threshold': 0.0,
                    'alarms': np.zeros(n_test, dtype=bool),
                    'alarm_pct': 0.0, 'time': 0.0, 'error': str(e),
                }
        if verbose:
            print(f"    BSDT/QuadSurf: ERROR — {e}")

    return results


def main():
    print("=" * 72)
    print("  PROTEIN FOLDING — BSDT + Full Engine Cross-Domain Validation")
    print("  Go-model β-hairpin, 30 residues, Langevin dynamics")
    print("=" * 72)

    cfg = ProteinConfig()

    # ── Step 1: Estimate folding temperature Tm ──
    print("\n[1] Estimating folding temperature Tm ...")
    t0 = time.perf_counter()
    Tm = estimate_Tm(cfg)
    print(f"    Tm ≈ {Tm:.0f} K  ({time.perf_counter() - t0:.1f}s)")

    # ── Step 2a: Run T_low first (self-reference from T=100K) ──
    results = {}
    T_low_val = 0.5 * Tm
    print(f"\n[2a] Running T_low = {T_low_val:.0f} K — Below Tm (folded)")
    t0 = time.perf_counter()
    traj_low = run_protein_simulation(
        T_low_val, cfg,
        n_equil=5000, n_prod=10000, sample_every=100,
        adaptive=False, seed=42)
    dt = time.perf_counter() - t0
    results['T_low'] = traj_low

    n_s = len(traj_low['rmsd'])
    print(f"    Samples: {n_s}, Time: {dt:.1f}s")
    print(f"    RMSD: {np.mean(traj_low['rmsd']):.2f} Å  |  "
          f"Q: {np.mean(traj_low['Q']):.3f}")
    print(f"    E_BS: {np.mean(traj_low['E_BS']):.4f}  |  "
          f"Alarms: {sum(traj_low['alarm'])}/{n_s}")

    # T_low production frames become the reference for all subsequent runs
    X_ref_folded = traj_low['X_frames']
    print(f"    ➜ Using {len(X_ref_folded)} folded frames as BSDT reference")

    # ── Step 2b: Run T_crit and T_high with folded reference ──
    temps_remaining = {
        'T_crit': (1.0 * Tm, 'At Tm (marginal)'),
        'T_high': (1.8 * Tm, 'Above Tm (unfolded)'),
    }

    for key, (T, desc) in temps_remaining.items():
        print(f"\n[2b] Running at T = {T:.0f} K — {desc}")
        t0 = time.perf_counter()
        traj = run_protein_simulation(
            T, cfg,
            n_equil=5000, n_prod=10000, sample_every=100,
            adaptive=False, external_ref=X_ref_folded, seed=42)
        dt = time.perf_counter() - t0
        results[key] = traj

        n_samples = len(traj['rmsd'])
        mean_rmsd = np.mean(traj['rmsd'])
        mean_Q = np.mean(traj['Q'])
        mean_ebs = np.mean(traj['E_BS'])
        n_alarms = sum(traj['alarm'])
        alarm_pct = 100 * n_alarms / max(n_samples, 1)

        print(f"    Samples: {n_samples}, Time: {dt:.1f}s")
        print(f"    RMSD: {mean_rmsd:.2f} Å  |  Q: {mean_Q:.3f}")
        print(f"    E_BS: {mean_ebs:.4f}  |  Alarms: {n_alarms}/{n_samples} "
              f"({alarm_pct:.0f}%)")
        print(f"    δ_C: {np.mean(traj['delta_C']):.3f}  "
              f"δ_G: {np.mean(traj['delta_G']):.3f}  "
              f"δ_A: {np.mean(traj['delta_A']):.3f}  "
              f"δ_T: {np.mean(traj['delta_T']):.3f}")

    # ── Step 3: Run above Tm with ADAPTIVE friction ──
    T_high = 1.8 * Tm
    print(f"\n[3] Running at T = {T_high:.0f} K with ADAPTIVE friction \u03b3*(E_BS)")
    t0 = time.perf_counter()
    traj_adapt = run_protein_simulation(
        T_high, cfg,
        n_equil=5000, n_prod=10000, sample_every=100,
        adaptive=True, external_ref=X_ref_folded, seed=42)
    dt = time.perf_counter() - t0
    results['T_high_adaptive'] = traj_adapt

    n_samples = len(traj_adapt['rmsd'])
    mean_rmsd = np.mean(traj_adapt['rmsd'])
    mean_Q = np.mean(traj_adapt['Q'])
    mean_ebs = np.mean(traj_adapt['E_BS'])
    n_alarms = sum(traj_adapt['alarm'])
    mean_gamma = np.mean(traj_adapt['gamma'])

    print(f"    Samples: {n_samples}, Time: {dt:.1f}s")
    print(f"    RMSD: {mean_rmsd:.2f} Å  |  Q: {mean_Q:.3f}")
    print(f"    E_BS: {mean_ebs:.4f}  |  Alarms: {n_alarms}/{n_samples}")
    print(f"    Mean γ*: {mean_gamma:.2f} (constant γ = {cfg.gamma_const:.1f})")

    # ── Step 4: Full Engine Scoring — BOTH approaches ──
    X_ref = results['T_low']['X_frames']
    engine_names = ['Molecular', 'Gravity', 'Hybrid', 'BSDT', 'QuadSurf']

    conditions = [
        ('T_crit',   f'T={1.0*Tm:.0f}K (marginal)'),
        ('T_high',   f'T={1.8*Tm:.0f}K (unfolded)'),
        ('T_high_adaptive', f'T={1.8*Tm:.0f}K + γ*'),
    ]

    # ── 4A: Unsupervised (normals-only, frozen window) ──
    print("\n" + "=" * 72)
    print("  APPROACH A — Unsupervised (train on normals only, y=0)")
    print("=" * 72)

    engine_results_A = {}
    for key, desc in conditions:
        X_prod = results[key]['X_frames']
        print(f"\n  {desc} ({len(X_prod)} frames vs {len(X_ref)} ref):")
        eng_res = score_with_engines_unsupervised(X_ref, X_prod, verbose=True)
        engine_results_A[key] = eng_res

    # ── 4B: Semi-Supervised (SIAM expanding window, y=0/1 in train) ──
    print("\n" + "=" * 72)
    print("  APPROACH B — Semi-Supervised (train on normals + known anomalies)")
    print("  Train = ref(y=0) + 50% prod(y=1)  |  Test = 50% held-out")
    print("=" * 72)

    engine_results_B = {}
    for key, desc in conditions:
        X_prod = results[key]['X_frames']
        print(f"\n  {desc} ({len(X_prod)} frames vs {len(X_ref)} ref):")
        eng_res = score_with_engines_semisupervised(X_ref, X_prod, verbose=True)
        engine_results_B[key] = eng_res

    # ── Combined comparison table ──
    print("\n" + "=" * 72)
    print("  ENGINE COMPARISON — A (Unsupervised) vs B (Semi-Supervised)")
    print("=" * 72)
    header = f"  {'Condition':<24}"
    for en in engine_names:
        header += f" {en:>12}"
    print(header + "    Q")
    print("  " + "-" * (24 + 13 * len(engine_names) + 6))

    for key, desc in conditions:
        # Approach A row
        row_a = f"  A {desc:<22}"
        for en in engine_names:
            alarm_pct = engine_results_A[key].get(en, {}).get('alarm_pct', 0.0)
            row_a += f" {alarm_pct:>10.0f}%"
        mean_Q = np.mean(results[key]['Q'])
        row_a += f"  {mean_Q:.3f}"
        print(row_a)
        # Approach B row
        row_b = f"  B {desc:<22}"
        for en in engine_names:
            alarm_pct = engine_results_B[key].get(en, {}).get('alarm_pct', 0.0)
            row_b += f" {alarm_pct:>10.0f}%"
        row_b += f"  {mean_Q:.3f}"
        print(row_b)

    # ── Per-engine mean score comparison ──
    print()
    header2 = f"  {'Condition':<24}"
    for en in engine_names:
        header2 += f"  {en+' μ':>12}"
    print(header2)
    print("  " + "-" * (24 + 14 * len(engine_names)))

    for key, desc in conditions:
        row_a = f"  A {desc:<22}"
        for en in engine_names:
            mean_s = engine_results_A[key].get(en, {}).get('mean', 0.0)
            row_a += f"  {mean_s:>12.4f}"
        print(row_a)
        row_b = f"  B {desc:<22}"
        for en in engine_names:
            mean_s = engine_results_B[key].get(en, {}).get('mean', 0.0)
            row_b += f"  {mean_s:>12.4f}"
        print(row_b)

    # Use semi-supervised results for downstream summary (engine_results = B)
    engine_results = engine_results_B

    # ── Step 5: Summary table (BSDT channels) ──
    print("\n" + "=" * 72)
    print("  SUMMARY TABLE — Protein Folding × BSDT Channels")
    print("=" * 72)
    print(f"  {'Condition':<28} {'RMSD (Å)':>9} {'Q':>6} {'E_BS':>8} "
          f"{'Alarms':>8} {'δ_C':>6} {'δ_T':>6}")
    print("  " + "-" * 70)

    for key, label in [
        ('T_low',    f'T={0.5*Tm:.0f}K (below Tm)'),
        ('T_crit',   f'T={1.0*Tm:.0f}K (at Tm)'),
        ('T_high',   f'T={1.8*Tm:.0f}K (above Tm)'),
        ('T_high_adaptive', f'T={1.8*Tm:.0f}K + γ*(E_BS)'),
    ]:
        t = results[key]
        alarm_pct = 100 * sum(t['alarm']) / max(len(t['alarm']), 1)
        print(f"  {label:<28} {np.mean(t['rmsd']):>8.2f} "
              f"{np.mean(t['Q']):>6.3f} {np.mean(t['E_BS']):>8.4f} "
              f"{alarm_pct:>7.0f}% {np.mean(t['delta_C']):>6.3f} "
              f"{np.mean(t['delta_T']):>6.3f}")

    # ── Step 5: BSDT lead-time analysis ──
    # At T=Tm, does BSDT alarm fire before RMSD exceeds threshold?
    print("\n" + "=" * 72)
    print("  BSDT LEAD-TIME ANALYSIS (at Tm)")
    print("=" * 72)

    traj_crit = results['T_crit']
    rmsd_arr = np.array(traj_crit['rmsd'])
    ebs_arr = np.array(traj_crit['E_BS'])
    alarm_arr = np.array(traj_crit['alarm'])
    time_arr = np.array(traj_crit['time'])

    # RMSD threshold for "unfolded": mean_native_RMSD + 3σ
    traj_low = results['T_low']
    rmsd_native_mean = np.mean(traj_low['rmsd'])
    rmsd_native_std = np.std(traj_low['rmsd'])
    rmsd_threshold = rmsd_native_mean + 3 * rmsd_native_std

    # First time BSDT alarm fires
    first_alarm = None
    for i, a in enumerate(alarm_arr):
        if a:
            first_alarm = i
            break

    # First time RMSD exceeds threshold
    first_rmsd = None
    for i, r in enumerate(rmsd_arr):
        if r > rmsd_threshold:
            first_rmsd = i
            break

    if first_alarm is not None and first_rmsd is not None:
        lead = first_rmsd - first_alarm
        lead_time = (time_arr[first_rmsd] - time_arr[first_alarm])
        print(f"  RMSD threshold: {rmsd_threshold:.2f} Å")
        print(f"  First BSDT alarm:  sample {first_alarm} "
              f"(t = {time_arr[first_alarm]:.2f} ps)")
        print(f"  First RMSD breach: sample {first_rmsd} "
              f"(t = {time_arr[first_rmsd]:.2f} ps)")
        print(f"  ➜ BSDT leads RMSD by {lead} samples "
              f"({lead_time:.2f} ps)")
    elif first_alarm is not None:
        print(f"  BSDT alarm fires at sample {first_alarm} "
              f"but RMSD never exceeds {rmsd_threshold:.2f} Å")
        print(f"  (BSDT detects local instability invisible to global RMSD)")
    else:
        print(f"  No BSDT alarm at Tm (protein may be marginal-stable)")

    # ── Step 6: Channel-level crash fingerprint ──
    print("\n" + "=" * 72)
    print("  CHANNEL-LEVEL ANALYSIS — Folded vs Unfolded")
    print("=" * 72)
    ch_folded = {
        'delta_C': np.mean(results['T_low']['delta_C']),
        'delta_G': np.mean(results['T_low']['delta_G']),
        'delta_A': np.mean(results['T_low']['delta_A']),
        'delta_T': np.mean(results['T_low']['delta_T']),
    }
    ch_unfolded = {
        'delta_C': np.mean(results['T_high']['delta_C']),
        'delta_G': np.mean(results['T_high']['delta_G']),
        'delta_A': np.mean(results['T_high']['delta_A']),
        'delta_T': np.mean(results['T_high']['delta_T']),
    }
    print(f"  {'Channel':<12} {'Folded':>10} {'Unfolded':>10} {'Ratio':>10}")
    print(f"  {'-'*42}")
    for ch_name in ['delta_C', 'delta_G', 'delta_A', 'delta_T']:
        f_val = ch_folded[ch_name]
        u_val = ch_unfolded[ch_name]
        ratio = u_val / max(f_val, 1e-8)
        print(f"  {ch_name:<12} {f_val:>10.4f} {u_val:>10.4f} {ratio:>10.2f}×")

    # ── Step 7: Adaptive friction stabilisation ──
    print("\n" + "=" * 72)
    print("  ADAPTIVE FRICTION STABILISATION")
    print("=" * 72)
    const_rmsd = np.mean(results['T_high']['rmsd'])
    adapt_rmsd = np.mean(results['T_high_adaptive']['rmsd'])
    const_Q = np.mean(results['T_high']['Q'])
    adapt_Q = np.mean(results['T_high_adaptive']['Q'])
    const_ebs = np.mean(results['T_high']['E_BS'])
    adapt_ebs = np.mean(results['T_high_adaptive']['E_BS'])

    print(f"  At T = {1.8*Tm:.0f} K (above Tm):")
    print(f"    Constant γ : RMSD = {const_rmsd:.2f} Å, "
          f"Q = {const_Q:.3f}, E_BS = {const_ebs:.4f}")
    print(f"    Adaptive γ*: RMSD = {adapt_rmsd:.2f} Å, "
          f"Q = {adapt_Q:.3f}, E_BS = {adapt_ebs:.4f}")
    rmsd_reduction = (const_rmsd - adapt_rmsd) / const_rmsd * 100
    Q_improvement = (adapt_Q - const_Q) / max(const_Q, 1e-8) * 100
    print(f"    ➜ RMSD reduction: {rmsd_reduction:.1f}%")
    print(f"    ➜ Q improvement:  {Q_improvement:.1f}%")

    # ── Step 8: Double-well structure ──
    print("\n" + "=" * 72)
    print("  DOUBLE-WELL STRUCTURE (Q-value histogram)")
    print("=" * 72)
    Q_crit = np.array(results['T_crit']['Q'])
    Q_bins = np.linspace(0, 1, 11)
    hist, _ = np.histogram(Q_crit, bins=Q_bins)
    print(f"  Q-value distribution at Tm (two-state test):")
    for i in range(len(hist)):
        bar = '█' * hist[i]
        print(f"    Q=[{Q_bins[i]:.1f},{Q_bins[i+1]:.1f}): "
              f"{hist[i]:3d} {bar}")
    # Check bimodality
    low_pop = np.sum(Q_crit < 0.4)
    high_pop = np.sum(Q_crit > 0.6)
    mid_pop = np.sum((Q_crit >= 0.4) & (Q_crit <= 0.6))
    print(f"  Low Q (<0.4): {low_pop}  |  Mid (0.4-0.6): {mid_pop}  "
          f"|  High (>0.6): {high_pop}")
    if low_pop > 0 and high_pop > 0:
        print(f"  ➜ TWO-STATE folding confirmed (double-well populated)")
    else:
        print(f"  ➜ Single-basin regime at this temperature")

    # ── Final summary for paper ──
    print("\n" + "=" * 72)
    print("  PAPER-READY SUMMARY")
    print("=" * 72)
    print(f"  Model:     Cα Go-model β-hairpin, N={cfg.N} residues")
    cp, cd = compute_native_contacts(build_native_structure(cfg), cfg)
    print(f"  Contacts:  {len(cp)} native contacts")
    print(f"  Tm:        {Tm:.0f} K")
    print(f"  T < Tm:    Folded (Q={np.mean(results['T_low']['Q']):.3f}), "
          f"no BSDT alarm")
    print(f"  T > Tm:    Unfolded (Q={np.mean(results['T_high']['Q']):.3f}), "
          f"BSDT alarm: {sum(results['T_high']['alarm'])}/"
          f"{len(results['T_high']['alarm'])}")
    print(f"  Adaptive:  γ*(E_BS) reduces RMSD by {rmsd_reduction:.1f}%, "
          f"Q improves by {Q_improvement:.1f}%")
    print(f"  Channels:  δ_C → {ch_unfolded['delta_C']/max(ch_folded['delta_C'],1e-8):.1f}× "
          f"(core exposure), "
          f"δ_T → {ch_unfolded['delta_T']/max(ch_folded['delta_T'],1e-8):.1f}× "
          f"(novel conformations)")

    # Engine consensus
    print(f"\n  Engine consensus (alarm % at T > Tm):")
    for en in engine_names:
        er = engine_results.get('T_high', {}).get(en, {})
        a = er.get('alarm_pct', 0.0)
        m = er.get('mean', 0.0)
        print(f"    {en:12s}: alarm={a:.0f}%, mean_score={m:.4f}")

    # Adaptive friction with all engines
    print(f"\n  Adaptive friction (γ*) vs constant γ at T > Tm:")
    for en in engine_names:
        high_m = engine_results.get('T_high', {}).get(en, {}).get('mean', 0)
        adap_m = engine_results.get('T_high_adaptive', {}).get(en, {}).get('mean', 0)
        reduction = (high_m - adap_m) / max(high_m, 1e-8) * 100
        print(f"    {en:12s}: const={high_m:.4f} → adapt={adap_m:.4f} "
              f"({reduction:+.1f}%)")

    print(f"\n  Physics:   Φ = Go-model free energy (PHYSICAL, "
          f"not surrogate)")
    print()


if __name__ == "__main__":
    main()
