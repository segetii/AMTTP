"""
quantum_engine.py -- Domain VII: Quantum Phase Transition Engine
=================================================================
Transverse-field Ising model with exact diagonalization + BSDT detection.

Physics:
  H = -J sum_{<ij>} sigma_z^i sigma_z^{i+1}  -  h sum_i sigma_x^i
  (1D chain, periodic boundary conditions)

  QPT at h_c = J (exact, Jordan-Wigner):
    h < J  :  ferromagnetic (ordered), physical gap > 0, Morse ind = 0
    h = J  :  quantum critical point, gap -> 0 as pi/N
    h > J  :  paramagnetic (disordered), gap > 0

  KEY SUBTLETY: The exact ground state preserves Z2 symmetry, so
  <sigma_z^i> = 0 for ALL h and N.  The order parameter is the
  SQUARED magnetisation m^2 = <(sum sigma_z)^2> / N^2, computed
  from correlations.  The Binder cumulant U detects the QPT as the
  N-independent crossing point.

  The spectral gap has two regimes:
    Ordered (h < J):  E1-E0 ~ exp(-alpha*N)  (tunnel splitting)
                      E2-E0 ~ 2(J-h)         (physical gap)
    Disordered (h > J): E1-E0 = 2(h-J)       (true gap)

  We use the PHYSICAL gap: max(E1-E0, E2-E1) robustly selects
  the correct quantity in both phases.

BSDT mapping:
  Phi_pair  = J sigma_z^i sigma_z^{i+1}  (Ising coupling)
  C*        = {h : physical gap = 0} = {h = J}
  gamma*(X) = J / |d^2 E_MF / dm^2|

Author: Odeyemi Olusegun Israel
"""
from __future__ import annotations
import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import eigsh
import warnings
warnings.filterwarnings('ignore')


# =====================================================================
#  TRANSVERSE-FIELD ISING MODEL -- EXACT DIAGONALIZATION
# =====================================================================

class TransverseFieldIsing:
    """
    1D transverse-field Ising model, PBC, exact diag.

    H = -J sum_i sigma_z^i sigma_z^{i+1}  -  h sum_i sigma_x^i

    Parameters
    ----------
    N : int     Number of qubits.  Hilbert space dim = 2^N.
    J : float   Ising coupling strength (ferromagnetic if > 0).
    """

    def __init__(self, N: int, J: float = 1.0):
        self.N = N
        self.J = J
        self.dim = 1 << N
        self._basis = np.arange(self.dim, dtype=np.int64)

        # sigma_z eigenvalue table: (dim, N)
        self._sz = (1 - 2 * ((self._basis[:, None] >>
                               np.arange(N)[None, :]) & 1)
                    ).astype(np.float64)

        # Total magnetisation M_z for each basis state: (dim,)
        self._Mz = self._sz.sum(axis=1).astype(np.float64)

        # Precompute ZZ diagonal (h-independent)
        self._zz_diag = self._compute_zz_diagonal()

        # sigma_x flip indices per site
        self._flip_idx = [self._basis ^ (1 << i) for i in range(N)]

    def _compute_zz_diagonal(self) -> np.ndarray:
        diag = np.zeros(self.dim, dtype=np.float64)
        for i in range(self.N):
            j = (i + 1) % self.N
            xi = (self._basis >> i) & 1
            xj = (self._basis >> j) & 1
            diag += -self.J * (1 - 2 * (xi ^ xj)).astype(np.float64)
        return diag

    def hamiltonian(self, h: float) -> sp.csr_matrix:
        N, dim = self.N, self.dim
        rows = np.tile(self._basis, N)
        cols = np.concatenate(self._flip_idx)
        vals = np.full(N * dim, -h, dtype=np.float64)
        H_off = sp.csr_matrix((vals, (rows, cols)), shape=(dim, dim))
        return H_off + sp.diags(self._zz_diag, format='csr')

    def solve(self, h: float, n_states: int = 6):
        """Lowest n_states eigenvalues and eigenvectors."""
        H = self.hamiltonian(h)
        if self.dim <= 512:
            Hd = H.toarray()
            evals, evecs = np.linalg.eigh(Hd)
            return evals[:n_states], evecs[:, :n_states]
        k = min(n_states, self.dim - 2)
        evals, evecs = eigsh(H, k=k, which='SA')
        idx = np.argsort(evals)
        return evals[idx], evecs[:, idx]

    def observables(self, h: float, psi=None, energies=None) -> dict:
        """
        Compute quantum observables from the ground state.

        Uses symmetry-correct order parameters:
          m_sq    = <M_z^2>/N^2  (squared magnetisation, from correlations)
          m_abs   = sqrt(m_sq)   (order parameter)
          C_zz    = <sigma_z^i sigma_z^{i+1}> (NN correlation)
          C_long  = <sigma_z^0 sigma_z^{N/2}> (long-range correlation)
          C_ratio = C_long / max(|C_zz|, eps)
          S_vN    = half-chain entanglement entropy
          gap_phys = physical excitation gap (NOT tunnel splitting)
          binder  = Binder cumulant U = 1 - <M^4>/(3<M^2>^2)
        """
        if psi is None or energies is None:
            energies, evecs = self.solve(h)
            psi = evecs[:, 0]

        N = self.N
        probs = np.abs(psi) ** 2

        # -- Squared magnetisation (order parameter) --
        Mz = self._Mz
        Mz2 = float(np.sum(probs * Mz ** 2))
        Mz4 = float(np.sum(probs * Mz ** 4))
        m_sq  = Mz2 / N ** 2
        m_abs = np.sqrt(max(m_sq, 0.0))

        # Binder cumulant: U = 1 - <M^4> / (3 <M^2>^2)
        binder = 1.0 - Mz4 / (3.0 * max(Mz2 ** 2, 1e-30))

        # -- NN ZZ correlation --
        czz = 0.0
        for i in range(N):
            j = (i + 1) % N
            czz += float(np.sum(probs * self._sz[:, i] * self._sz[:, j]))
        czz /= N

        # -- Long-range correlation --
        half = N // 2
        c_long = float(np.sum(probs * self._sz[:, 0] * self._sz[:, half]))

        # -- Correlation ratio --
        c_ratio = c_long / (abs(czz) + 1e-12)

        # -- <sigma_x> --
        mx_total = 0.0
        for i in range(N):
            mx_total += float(np.real(np.sum(
                np.conj(psi) * psi[self._flip_idx[i]])))
        m_x = mx_total / N

        # -- Entanglement entropy --
        svn = self._entanglement_entropy(psi)

        # -- Physical gap --
        # max(E1-E0, E2-E1) selects physical gap in both phases.
        if len(energies) >= 3:
            g01 = energies[1] - energies[0]
            g12 = energies[2] - energies[1]
            gap_phys = float(max(g01, g12))
            gap_01   = float(g01)
        elif len(energies) >= 2:
            gap_phys = float(energies[1] - energies[0])
            gap_01   = gap_phys
        else:
            gap_phys = gap_01 = 0.0

        # -- IPR --
        ipr = float(np.sum(probs ** 2))

        # -- Energy per site --
        e0 = float(energies[0]) / N

        return dict(
            m_sq=m_sq, m_abs=m_abs, m_x=m_x,
            C_zz=czz, C_long=c_long, C_ratio=c_ratio,
            S_vN=svn, gap_phys=gap_phys, gap_01=gap_01,
            e0=e0, IPR=ipr, binder=binder,
        )

    def _entanglement_entropy(self, psi: np.ndarray) -> float:
        Na = self.N // 2
        Nb = self.N - Na
        psi_mat = psi.reshape(1 << Nb, 1 << Na)
        s = np.linalg.svd(psi_mat, compute_uv=False)
        s2 = s ** 2
        s2 = s2[s2 > 1e-30]
        return float(-np.sum(s2 * np.log(s2)))

    def fidelity(self, psi1, psi2) -> float:
        return float(np.abs(np.vdot(psi1, psi2)) ** 2)

    @staticmethod
    def exact_hc(J: float = 1.0) -> float:
        return J


# =====================================================================
#  MEAN-FIELD VARIATIONAL ANALYSIS
# =====================================================================

class MeanFieldIsing:
    """
    E_MF(m) = -z J m^2  -  h sqrt(1 - m^2),   z = coordination number.
    MF h_c = zJ (overestimates exact h_c = J for 1D).
    """

    def __init__(self, J: float = 1.0, z: int = 2):
        self.J = J
        self.z = z
        self.hc_mf = z * J

    def energy(self, m, h):
        return -self.z * self.J * m ** 2 - h * np.sqrt(np.maximum(1 - m ** 2, 1e-30))

    def hessian_at(self, m: float, h: float) -> float:
        s = max(1 - m ** 2, 1e-30)
        return -2.0 * self.z * self.J + h / s ** 1.5

    def ordered_minimum(self, h: float) -> float:
        if h >= self.hc_mf - 1e-12:
            return 0.0
        ratio = h / (2 * self.z * self.J)
        return np.sqrt(max(1 - ratio ** 2, 0.0))

    def hessian_at_minimum(self, h: float) -> float:
        return self.hessian_at(self.ordered_minimum(h), h)

    def morse_index_exact(self, h: float, J: float = None) -> int:
        """Morse index using exact h_c = J."""
        if J is None:
            J = self.J
        return 0 if h < J else 1

    def adaptive_gamma(self, h: float) -> float:
        hess = abs(self.hessian_at_minimum(h))
        return self.J / max(hess, 1e-10)


# =====================================================================
#  QUANTUM BSDT -- 4-channel scorer
# =====================================================================

class QuantumBSDT:
    """
    BSDT 4-channel scorer for quantum phase transitions.

    All channels use Z2-symmetry-correct observables:

    delta_C  Camouflage : sqrt(m_sq) * S_vN / S_max
             System looks ordered (m_sq high) but entanglement growing.
    delta_G  Gap (corr.) : 1 - C_ratio = 1 - C_long/C_zz
             Long-range correlations decaying before short-range.
    delta_A  Activity    : 1 / (1 + gap_phys)
             Inverse physical gap = susceptibility proxy.
    delta_T  Temporal    : 1 - |<psi_ref|psi>|^2
             Infidelity with reference ground state.
    """

    def __init__(self):
        self._psi_ref = None
        self._S_max = None
        self._ref_mean = None
        self._ref_std = None
        self._weights = None

    def _channels(self, obs: dict, psi: np.ndarray) -> np.ndarray:
        delta_C = obs['m_abs'] * obs['S_vN'] / max(self._S_max, 1e-10)
        delta_G = max(1.0 - obs['C_ratio'], 0.0)
        delta_A = 1.0 / (1.0 + obs['gap_phys'])
        F = float(np.abs(np.vdot(self._psi_ref, psi)) ** 2)
        delta_T = 1.0 - F
        return np.array([delta_C, delta_G, delta_A, delta_T])

    def fit(self, obs_list: list, psi_list: list, N: int):
        self._psi_ref = psi_list[0].copy()
        self._S_max = (N / 2) * np.log(2)

        feats = np.array([
            self._channels(obs, psi)
            for obs, psi in zip(obs_list, psi_list)
        ])
        self._ref_mean = feats.mean(axis=0)
        self._ref_std  = feats.std(axis=0) + 1e-10

        # Fisher VR weights
        z    = (feats - self._ref_mean) / self._ref_std
        zpos = np.maximum(z, 0)
        tot  = zpos.sum(axis=1)
        p80  = np.percentile(tot, 80)
        p50  = np.percentile(tot, 50)
        hi, lo = tot >= p80, tot <= p50
        K = feats.shape[1]
        if hi.sum() >= 2 and lo.sum() >= 2:
            fr = np.zeros(K)
            for k in range(K):
                mu_h = zpos[hi, k].mean()
                mu_l = zpos[lo, k].mean()
                v_h  = zpos[hi, k].var()
                v_l  = zpos[lo, k].var()
                fr[k] = (mu_h - mu_l) ** 2 / max(v_h + v_l, 1e-10)
            s = fr.sum()
            self._weights = fr / s if s > 1e-10 else np.ones(K) / K
        else:
            self._weights = np.ones(K) / K
        return self

    def score(self, obs: dict, psi: np.ndarray) -> float:
        feats = self._channels(obs, psi)
        z = (feats - self._ref_mean) / self._ref_std
        return float(np.maximum(z, 0) @ self._weights)

    def score_batch(self, obs_list: list, psi_list: list) -> np.ndarray:
        return np.array([
            self.score(obs, psi) for obs, psi in zip(obs_list, psi_list)
        ])

    def ebs(self, obs: dict, psi: np.ndarray) -> float:
        feats = self._channels(obs, psi)
        return float(np.sum(self._weights * feats ** 2))

    def channel_detail(self, obs: dict, psi: np.ndarray) -> dict:
        feats = self._channels(obs, psi)
        return dict(zip(['delta_C', 'delta_G', 'delta_A', 'delta_T'], feats.tolist()))


# =====================================================================
#  MFLS — Multi-Factor Latent Score gradient
# =====================================================================

def compute_mfls(h_vals: np.ndarray, ebs_scores: np.ndarray) -> np.ndarray:
    """
    MFLS = |dE_BS/dh| — gradient of blind-spot energy.

    E_BS monotonically separates ordered from disordered phases.
    The MFLS peaks WHERE the transition occurs (where E_BS changes
    fastest), which is the alarm signal in the BSDT framework.

    This mirrors the financial MFLS: the alarm fires when the
    rate of risk accumulation spikes, not when risk is simply high.
    """
    return np.abs(np.gradient(ebs_scores, h_vals))


def compute_obs_gradient_norm(obs_list: list, h_vals: np.ndarray,
                              keys: list = None) -> np.ndarray:
    """
    Model-free multi-observable gradient norm: ||d(obs)/dh||.

    Each observable is normalised to [0,1] so no single quantity
    dominates.  Peaks where observables change most rapidly — the
    phase transition.
    """
    if keys is None:
        keys = ['m_abs', 'S_vN', 'C_ratio', 'gap_phys', 'binder']
    mat = np.array([[o[k] for k in keys] for o in obs_list], dtype=np.float64)
    for j in range(mat.shape[1]):
        lo, hi = mat[:, j].min(), mat[:, j].max()
        rng = hi - lo
        if rng > 1e-10:
            mat[:, j] = (mat[:, j] - lo) / rng
    grad = np.gradient(mat, h_vals, axis=0)
    return np.sqrt(np.sum(grad ** 2, axis=1))


# =====================================================================
#  GEOMETRIC PIPELINE BRIDGE
# =====================================================================

def observables_to_feature_matrix(obs_list: list) -> np.ndarray:
    """
    (n_steps, 5) for GeometricFusedScorer.
    Columns: [m_abs, m_x, C_zz, S_vN, gap_phys]
    """
    rows = []
    for obs in obs_list:
        rows.append([
            obs['m_abs'], obs['m_x'], obs['C_zz'],
            obs['S_vN'], obs['gap_phys'],
        ])
    return np.array(rows, dtype=np.float64)


# =====================================================================
#  SWEEP UTILITIES
# =====================================================================

def sweep_field(model: TransverseFieldIsing, h_values: np.ndarray,
                n_states: int = 6, verbose: bool = False):
    results = []
    for i, h in enumerate(h_values):
        energies, evecs = model.solve(h, n_states=n_states)
        psi = evecs[:, 0]
        obs = model.observables(h, psi=psi, energies=energies)
        results.append(dict(h=float(h), obs=obs, psi=psi, energies=energies))
        if verbose and (i % 20 == 0 or i == len(h_values) - 1):
            print(f"  h/J={h:.3f}  m={obs['m_abs']:.3f}  gap={obs['gap_phys']:.4f}  "
                  f"S={obs['S_vN']:.3f}  C_r={obs['C_ratio']:.3f}  "
                  f"U={obs['binder']:.3f}")
    return results


def label_qpt(h_values, J=1.0, width=0.15):
    return (np.abs(h_values / J - 1.0) < width).astype(int)

def label_postqpt(h_values, J=1.0):
    return (h_values > J).astype(int)
