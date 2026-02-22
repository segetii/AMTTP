"""
N-Body Gravity Pull Clustering Engine
======================================
Physics-inspired gravitational clustering for anomaly detection.

Each data point is treated as a particle in an N-body system subject to:
  1. Radial pull toward the global centre (spring-like restoring force)
  2. Pairwise interaction: short-range attraction + close-range repulsion
  3. (Optional) Operator deviation pull from UDL spectrum operators

The system evolves via discrete Euler integration:
    X^{t+1} = X^t + η · F(X^t)

After convergence, points in the same energy basin cluster together;
outliers drift to high-energy orbits or isolated positions.

Formula
-------
F_i = −α(x_i − μ)                       [radial anchoring]
    − γ Σ_{j≠i} ∇K(x_i − x_j)          [pairwise interaction]
    − Σ_k β_k DΦ_k(x_i)^T D_k(x_i)     [operator deviation, optional]

Interaction kernel:
    K(r) = −exp(−r²/σ²) + λ/(r + ε)     [attraction + repulsion]

Author: Odeyemi Olusegun Israel
"""

from __future__ import annotations

import numpy as np
from sklearn.preprocessing import StandardScaler
from typing import Optional, List, Tuple, Dict


# ---------------------------------------------------------------------------
# Interaction kernels
# ---------------------------------------------------------------------------

def _pairwise_forces_loop(X: np.ndarray,
                          gamma: float = 1.0,
                          sigma: float = 1.0,
                          lambda_rep: float = 0.1,
                          eps: float = 1e-5) -> np.ndarray:
    """O(n²) pairwise interaction forces — loop version (reference).

    Parameters
    ----------
    X : (n, d) array
    gamma : interaction strength
    sigma : attraction length-scale
    lambda_rep : repulsion coefficient
    eps : softening to avoid division by zero

    Returns
    -------
    forces : (n, d) array — net pairwise force on each particle
    """
    n = X.shape[0]
    forces = np.zeros_like(X)

    for i in range(n):
        diff = X[i] - X                         # (n, d)
        dist = np.linalg.norm(diff, axis=1, keepdims=True) + eps  # (n, 1)

        # Attraction: pulls neighbours within σ closer
        attraction = np.exp(-(dist ** 2) / (sigma ** 2))     # (n, 1)

        # Repulsion: prevents collapse at short range
        repulsion = lambda_rep / dist                         # (n, 1)

        # Net force magnitude (negative = attractive direction)
        magnitude = -gamma * (attraction - repulsion)         # (n, 1)

        # Direction-weighted sum (skip self via zero diff[i])
        forces[i] = np.sum(magnitude * (diff / dist), axis=0)

    return forces


def _pairwise_forces_vec(X: np.ndarray,
                         gamma: float = 1.0,
                         sigma: float = 1.0,
                         lambda_rep: float = 0.1,
                         eps: float = 1e-5) -> np.ndarray:
    """O(n²) pairwise interaction forces — fully vectorised.

    Broadcasts the full (n, n, d) difference tensor.
    Uses more memory but ~10-50× faster than the loop version.
    Falls back to the loop version if n > 5000 to cap memory.
    """
    n, d = X.shape
    # diff[i, j] = X[i] - X[j]   shape (n, n, d)
    diff = X[:, None, :] - X[None, :, :]                     # (n, n, d)
    dist = np.linalg.norm(diff, axis=2, keepdims=True) + eps  # (n, n, 1)

    attraction = np.exp(-(dist ** 2) / (sigma ** 2))          # (n, n, 1)
    repulsion = lambda_rep / dist                              # (n, n, 1)
    magnitude = -gamma * (attraction - repulsion)              # (n, n, 1)

    unit = diff / dist                                         # (n, n, d)
    forces = np.sum(magnitude * unit, axis=1)                  # (n, d)
    return forces


def pairwise_forces(X: np.ndarray,
                    gamma: float = 1.0,
                    sigma: float = 1.0,
                    lambda_rep: float = 0.1,
                    eps: float = 1e-5) -> np.ndarray:
    """Compute pairwise N-body interaction forces.

    Auto-selects vectorised or loop implementation based on n.

    Parameters
    ----------
    X : (n, d) array — current particle positions
    gamma : interaction strength multiplier
    sigma : attraction Gaussian length-scale
    lambda_rep : short-range repulsion coefficient
    eps : softening constant

    Returns
    -------
    forces : (n, d) array
    """
    n = X.shape[0]
    if n <= 5000:
        return _pairwise_forces_vec(X, gamma, sigma, lambda_rep, eps)
    return _pairwise_forces_loop(X, gamma, sigma, lambda_rep, eps)


# ---------------------------------------------------------------------------
# Radial pull
# ---------------------------------------------------------------------------

def radial_pull(X: np.ndarray, mu: np.ndarray, alpha: float = 0.1) -> np.ndarray:
    """Spring-like restoring force toward the global centre.

    F_radial = −α (x_i − μ)

    Parameters
    ----------
    X : (n, d) array
    mu : (d,) array — global centroid
    alpha : spring constant

    Returns
    -------
    force : (n, d) array
    """
    return -alpha * (X - mu)


# ---------------------------------------------------------------------------
# Operator deviation pull (optional extension)
# ---------------------------------------------------------------------------

def operator_deviation_pull(X: np.ndarray,
                            mu: np.ndarray,
                            operators: Optional[list] = None,
                            betas: Optional[np.ndarray] = None) -> np.ndarray:
    """Deviation force from UDL spectrum operators.

    F_op = −Σ_k β_k · (Φ_k(x)² − Φ_k(μ)²)   [quadratic approximation]

    Parameters
    ----------
    X : (n, d) array
    mu : (d,) array
    operators : list of (name, operator) tuples with .transform()
    betas : per-operator weights (defaults to uniform 1/K)

    Returns
    -------
    force : (n, d) array — operator-induced restoring force
    """
    if operators is None:
        return np.zeros_like(X)

    K = len(operators)
    if betas is None:
        betas = np.ones(K) / K

    force = np.zeros_like(X)
    mu_row = mu.reshape(1, -1)

    for k, (name, op) in enumerate(operators):
        try:
            phi_x = op.transform(X)         # (n, d_k)
            phi_mu = op.transform(mu_row)    # (1, d_k)
            # Quadratic deviation: Φ(x)² − Φ(μ)²  projected back to input space
            # Simplified: use raw difference scaled to input dimension
            dev = phi_x - phi_mu             # (n, d_k)
            # Project back: pad/truncate to input dim
            d_in = X.shape[1]
            d_k = dev.shape[1]
            if d_k >= d_in:
                contrib = dev[:, :d_in]
            else:
                contrib = np.zeros_like(X)
                contrib[:, :d_k] = dev
            force -= betas[k] * contrib
        except Exception:
            continue

    return force


# ---------------------------------------------------------------------------
# Total force
# ---------------------------------------------------------------------------

def total_force(X: np.ndarray,
                mu: np.ndarray,
                alpha: float = 0.1,
                gamma: float = 1.0,
                sigma: float = 1.0,
                lambda_rep: float = 0.1,
                operators: Optional[list] = None,
                betas: Optional[np.ndarray] = None,
                eps: float = 1e-5) -> np.ndarray:
    """Sum of all force components on each particle.

    F_i = F_radial + F_pairwise + F_operator

    Parameters
    ----------
    X, mu, alpha, gamma, sigma, lambda_rep : see component functions
    operators : optional UDL spectrum operators for deviation pull
    betas : per-operator weights
    eps : softening constant

    Returns
    -------
    F : (n, d) array — total force
    """
    F = radial_pull(X, mu, alpha)
    F += pairwise_forces(X, gamma, sigma, lambda_rep, eps)
    if operators is not None:
        F += operator_deviation_pull(X, mu, operators, betas)
    return F


# ---------------------------------------------------------------------------
# Energy monitoring
# ---------------------------------------------------------------------------

def compute_system_energy(X: np.ndarray,
                          mu: np.ndarray,
                          alpha: float,
                          gamma: float,
                          sigma: float,
                          lambda_rep: float,
                          eps: float = 1e-5) -> Dict[str, float]:
    """Compute the total potential energy of the particle system.

    E = E_radial + E_interaction

    E_radial    = (α/2) Σ_i ||x_i − μ||²
    E_attract   = −(γ/2) Σ_{i≠j} exp(−r²/σ²)
    E_repel     = (γ·λ/2) Σ_{i≠j} log(r + ε)
    E_total     = E_radial + E_attract + E_repel

    Returns dict with per-component and total energy.
    """
    n = X.shape[0]

    # Radial energy
    disp = X - mu                                    # (n, d)
    E_radial = 0.5 * alpha * np.sum(disp ** 2)

    # Pairwise energy (vectorised for n ≤ 5000, loop otherwise)
    if n <= 5000:
        diff = X[:, None, :] - X[None, :, :]         # (n, n, d)
        dist = np.linalg.norm(diff, axis=2) + eps     # (n, n)
        # Zero self-interactions on diagonal
        np.fill_diagonal(dist, eps)

        # Attraction potential
        E_attract = -0.5 * gamma * np.sum(np.exp(-(dist ** 2) / (sigma ** 2)))
        # Remove self-interaction contribution
        E_attract += 0.5 * gamma * n * np.exp(0.0)   # self-terms were exp(0)=1

        # Repulsion potential
        E_repel = 0.5 * gamma * lambda_rep * np.sum(np.log(dist))
        # Remove diagonal log(eps) contribution
        E_repel -= 0.5 * gamma * lambda_rep * n * np.log(eps)
    else:
        E_attract = 0.0
        E_repel = 0.0
        for i in range(n):
            diff_i = X[i] - X[i + 1:]
            dist_i = np.linalg.norm(diff_i, axis=1) + eps
            E_attract -= gamma * np.sum(np.exp(-(dist_i ** 2) / (sigma ** 2)))
            E_repel += gamma * lambda_rep * np.sum(np.log(dist_i))

    E_total = E_radial + E_attract + E_repel

    return {
        "total": float(E_total),
        "radial": float(E_radial),
        "attraction": float(E_attract),
        "repulsion": float(E_repel),
        "per_particle": float(E_total / max(n, 1)),
    }


# ---------------------------------------------------------------------------
# Main gravity engine
# ---------------------------------------------------------------------------

class GravityEngine:
    """N-body gravitational clustering engine.

    Evolves a particle system under radial + pairwise forces via
    discrete Euler integration and produces anomaly scores.

    Parameters
    ----------
    alpha : float
        Radial pull toward global centre (spring constant).
    gamma : float
        Pairwise interaction strength.
    sigma : float
        Attraction Gaussian length-scale.
    lambda_rep : float
        Short-range repulsion coefficient.
    eta : float
        Step size (learning rate) for Euler integration.
    iterations : int
        Number of discrete time steps.
    normalize : bool
        Whether to StandardScaler the input before simulation.
    track_energy : bool
        Whether to record system energy at each step.
    convergence_tol : float
        Early stopping if max displacement < tol. Set 0 to disable.

    Attributes
    ----------
    scaler_ : StandardScaler (fitted if normalize=True)
    mu_ : (d,) centroid of the (normalised) training data
    X_initial_ : (n, d) input positions (after normalisation)
    X_final_ : (n, d) final positions after simulation
    energy_history_ : list of dicts — per-step energy (if track_energy)
    displacement_history_ : list of float — max displacement per step
    converged_at_ : int or None — iteration where convergence was reached
    """

    def __init__(self,
                 alpha: float = 0.1,
                 gamma: float = 1.0,
                 sigma: float = 1.0,
                 lambda_rep: float = 0.1,
                 eta: float = 0.01,
                 iterations: int = 100,
                 normalize: bool = True,
                 track_energy: bool = True,
                 convergence_tol: float = 1e-6):
        self.alpha = alpha
        self.gamma = gamma
        self.sigma = sigma
        self.lambda_rep = lambda_rep
        self.eta = eta
        self.iterations = iterations
        self.normalize = normalize
        self.track_energy = track_energy
        self.convergence_tol = convergence_tol

        # Will be set during fit / run
        self.scaler_: Optional[StandardScaler] = None
        self.mu_: Optional[np.ndarray] = None
        self.X_initial_: Optional[np.ndarray] = None
        self.X_final_: Optional[np.ndarray] = None
        self.energy_history_: List[Dict[str, float]] = []
        self.displacement_history_: List[float] = []
        self.converged_at_: Optional[int] = None

    # ----- core simulation -----

    def fit_transform(self, X: np.ndarray,
                      operators: Optional[list] = None,
                      betas: Optional[np.ndarray] = None) -> np.ndarray:
        """Run the gravity simulation and return final positions.

        Parameters
        ----------
        X : (n, d) array — input data
        operators : optional list of (name, spectrum_op) for deviation pull
        betas : per-operator weights

        Returns
        -------
        X_final : (n, d) array — evolved positions
        """
        # Step 1 — Normalize
        if self.normalize:
            self.scaler_ = StandardScaler()
            X_work = self.scaler_.fit_transform(X).astype(np.float64)
        else:
            X_work = X.astype(np.float64).copy()

        self.X_initial_ = X_work.copy()

        # Step 2 — Global centre
        self.mu_ = np.mean(X_work, axis=0)

        # Step 6 — Iterative update
        self.energy_history_ = []
        self.displacement_history_ = []
        self.converged_at_ = None

        for t in range(self.iterations):
            # Energy snapshot (before step)
            if self.track_energy:
                E = compute_system_energy(
                    X_work, self.mu_, self.alpha, self.gamma,
                    self.sigma, self.lambda_rep,
                )
                E["step"] = t
                self.energy_history_.append(E)

            # Compute total force
            F = total_force(
                X_work, self.mu_,
                alpha=self.alpha,
                gamma=self.gamma,
                sigma=self.sigma,
                lambda_rep=self.lambda_rep,
                operators=operators,
                betas=betas,
            )

            # Euler step
            dX = self.eta * F
            X_work += dX

            # Convergence check
            max_disp = float(np.max(np.abs(dX)))
            self.displacement_history_.append(max_disp)

            if self.convergence_tol > 0 and max_disp < self.convergence_tol:
                self.converged_at_ = t + 1
                # Final energy snapshot
                if self.track_energy:
                    E = compute_system_energy(
                        X_work, self.mu_, self.alpha, self.gamma,
                        self.sigma, self.lambda_rep,
                    )
                    E["step"] = t + 1
                    self.energy_history_.append(E)
                break

        self.X_final_ = X_work
        return X_work

    # ----- scoring -----

    def anomaly_scores(self, X_final: Optional[np.ndarray] = None) -> np.ndarray:
        """Compute anomaly scores as distance from centre after dynamics.

        Parameters
        ----------
        X_final : (n, d) array. If None, uses self.X_final_.

        Returns
        -------
        scores : (n,) array — higher = more anomalous
        """
        if X_final is None:
            X_final = self.X_final_
        if X_final is None:
            raise RuntimeError("Call fit_transform() first.")
        return np.linalg.norm(X_final - self.mu_, axis=1)

    def displacement_scores(self) -> np.ndarray:
        """How far each point moved during the simulation.

        Normal points in dense regions move little; outliers drift far.

        Returns
        -------
        scores : (n,) array — total displacement per particle
        """
        if self.X_initial_ is None or self.X_final_ is None:
            raise RuntimeError("Call fit_transform() first.")
        return np.linalg.norm(self.X_final_ - self.X_initial_, axis=1)

    def cluster_labels(self, n_clusters: int = 2,
                       method: str = "kmeans") -> np.ndarray:
        """Cluster the final positions.

        Parameters
        ----------
        n_clusters : number of clusters
        method : 'kmeans' or 'dbscan'

        Returns
        -------
        labels : (n,) int array
        """
        if self.X_final_ is None:
            raise RuntimeError("Call fit_transform() first.")

        if method == "kmeans":
            from sklearn.cluster import KMeans
            return KMeans(n_clusters=n_clusters,
                          random_state=42, n_init=10).fit_predict(self.X_final_)
        elif method == "dbscan":
            from sklearn.cluster import DBSCAN
            return DBSCAN(eps=0.5, min_samples=5).fit_predict(self.X_final_)
        else:
            raise ValueError(f"Unknown clustering method: {method}")

    # ----- diagnostics -----

    def convergence_summary(self) -> Dict:
        """Return convergence diagnostics.

        Returns
        -------
        dict with keys:
            converged : bool
            converged_at : int or None
            iterations_run : int
            final_max_displacement : float
            energy_drop : float (E_final − E_initial)
            energy_initial / energy_final : float
        """
        n_steps = len(self.displacement_history_)
        summary = {
            "converged": self.converged_at_ is not None,
            "converged_at": self.converged_at_,
            "iterations_run": n_steps,
            "final_max_displacement": (
                self.displacement_history_[-1] if self.displacement_history_ else float("nan")
            ),
        }

        if self.energy_history_ and len(self.energy_history_) >= 2:
            summary["energy_initial"] = self.energy_history_[0]["total"]
            summary["energy_final"] = self.energy_history_[-1]["total"]
            summary["energy_drop"] = (
                self.energy_history_[-1]["total"] - self.energy_history_[0]["total"]
            )
        else:
            summary["energy_initial"] = float("nan")
            summary["energy_final"] = float("nan")
            summary["energy_drop"] = float("nan")

        return summary

    def print_summary(self) -> None:
        """Pretty-print convergence diagnostics."""
        s = self.convergence_summary()
        print("=" * 55)
        print("  Gravity Engine — Convergence Summary")
        print("=" * 55)
        print(f"  Iterations run   : {s['iterations_run']}")
        if s["converged"]:
            print(f"  Converged at     : step {s['converged_at']}")
        else:
            print(f"  Converged        : No (max iter reached)")
        print(f"  Final max |dX|   : {s['final_max_displacement']:.2e}")
        print(f"  Energy initial   : {s['energy_initial']:.4f}")
        print(f"  Energy final     : {s['energy_final']:.4f}")
        print(f"  Energy drop      : {s['energy_drop']:.4f}")
        print("=" * 55)

    def __repr__(self) -> str:
        return (
            f"GravityEngine(α={self.alpha}, γ={self.gamma}, σ={self.sigma}, "
            f"λ_rep={self.lambda_rep}, η={self.eta}, T={self.iterations})"
        )


# ---------------------------------------------------------------------------
# Convenience function (matches user's pseudocode exactly)
# ---------------------------------------------------------------------------

def run_gravity_clustering(X: np.ndarray,
                           alpha: float = 0.1,
                           gamma: float = 1.0,
                           sigma: float = 1.0,
                           lambda_rep: float = 0.1,
                           eta: float = 0.01,
                           iterations: int = 100,
                           normalize: bool = True) -> np.ndarray:
    """One-call gravity simulation — returns final positions.

    Equivalent to:
        engine = GravityEngine(...)
        return engine.fit_transform(X)

    Parameters
    ----------
    X : (n, d) array — input data
    alpha, gamma, sigma, lambda_rep, eta, iterations : hyperparameters
    normalize : whether to StandardScaler the input

    Returns
    -------
    X_final : (n, d) array — evolved positions
    """
    engine = GravityEngine(
        alpha=alpha, gamma=gamma, sigma=sigma,
        lambda_rep=lambda_rep, eta=eta, iterations=iterations,
        normalize=normalize, track_energy=False,
    )
    return engine.fit_transform(X)
