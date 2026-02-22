"""
Deviation-Induced Energy Functional
=====================================
Implements a geometric theory of anomaly equilibrium where:

  - Normal data are **stable equilibria** of a composite energy functional
  - Anomalies are **unstable** — they cannot simultaneously minimise
    all law-domain deviation energies

The energy functional has three components:

  E(x) = (α/2)||x − μ||²          ... radial anchoring
        + Σ_k (β_k/2)||Φ_k(x) − Φ_k(μ)||²   ... law deviation
        + (γ/2) Σ_{j≠i} W(x_i, x_j)          ... density interaction

The induced flow  ẋ = −∇E(x)  drives normal points to stable basins
and ejects anomalies to high-energy regions.

This module provides:
  - DeviationEnergy: compute per-point energy scores
  - OperatorDiversity: verify deviation-separating condition
  - EnergyFlow: iterative gradient-flow clustering (N-body system)

Theoretical Foundation
----------------------
Theorem (Deviation-Separating Family):
  If {Φ_k} satisfy  ∩_k ker(DΦ_k(μ)) = {0},
  then no non-zero perturbation from μ is invisible to all operators.
  Equivalently: anomalies have strictly higher energy than the
  normal equilibrium manifold.

Reference: UDL Framework — Odeyemi Olusegun Israel
"""

import numpy as np
from scipy.spatial.distance import cdist


# ═══════════════════════════════════════════════════════════════════
#  OPERATOR DIVERSITY — Deviation-Separating Condition
# ═══════════════════════════════════════════════════════════════════

class OperatorDiversity:
    """
    Measures whether a family of spectrum operators {Φ_k} forms a
    deviation-separating set — i.e., no perturbation direction is
    invisible to ALL operators simultaneously.

    The key condition:
        ∩_k ker(DΦ_k(μ)) = {0}

    This is verified numerically by:
    1. Computing Jacobians DΦ_k at the reference point μ
    2. Stacking all Jacobians vertically
    3. Checking that the stacked matrix has full column rank

    Additionally computes:
    - Per-operator nullspace dimension (blind directions)
    - Pairwise canonical correlations (redundancy)
    - Effective diversity index (how many independent views)
    """

    def __init__(self, perturbation_scale=1e-4):
        """
        Parameters
        ----------
        perturbation_scale : float
            Step size for finite-difference Jacobian estimation.
        """
        self.eps = perturbation_scale
        self.jacobians_ = None
        self.stacked_jacobian_ = None
        self.diversity_metrics_ = None

    def compute(self, operators, X_ref, mu=None):
        """
        Assess operator diversity at reference point.

        Parameters
        ----------
        operators : list of (name, operator) tuples
            Fitted spectrum operators with transform() method.
        X_ref : ndarray (N, m)
            Reference (normal) data used to fit operators.
        mu : ndarray (m,) or None
            Reference centroid. If None, uses mean of X_ref.

        Returns
        -------
        report : dict with keys:
            'is_separating': bool — whether family is deviation-separating
            'stacked_rank': int — rank of stacked Jacobian
            'input_dim': int — m (raw feature dimension)
            'null_intersection_dim': int — dim of shared nullspace (0 = good)
            'per_operator': list of dicts per operator
            'pairwise_correlation': ndarray (K, K) — redundancy matrix
            'diversity_index': float — effective number of independent views
        """
        if mu is None:
            mu = X_ref.mean(axis=0)

        m = len(mu)
        K = len(operators)

        # ── 1. Compute numerical Jacobians via finite differences ──
        self.jacobians_ = []
        operator_reports = []

        for name, op in operators:
            J = self._numerical_jacobian(op, mu, m)
            self.jacobians_.append(J)

            # Per-operator analysis
            _, S, _ = np.linalg.svd(J, full_matrices=False)
            rank = int(np.sum(S > 1e-8 * S[0])) if len(S) > 0 and S[0] > 0 else 0
            nullity = m - rank

            operator_reports.append({
                'name': name,
                'output_dim': J.shape[0],
                'rank': rank,
                'nullity': nullity,  # blind directions for this operator
                'singular_values': S.tolist(),
                'condition_number': float(S[0] / (S[-1] + 1e-15)) if len(S) > 0 else np.inf,
            })

        # ── 2. Stack all Jacobians and check combined rank ──
        self.stacked_jacobian_ = np.vstack(self.jacobians_)
        _, S_all, Vt_all = np.linalg.svd(self.stacked_jacobian_, full_matrices=False)
        stacked_rank = int(np.sum(S_all > 1e-8 * S_all[0])) if len(S_all) > 0 else 0
        null_dim = m - stacked_rank
        is_separating = (null_dim == 0)

        # ── 3. Pairwise canonical correlations (redundancy) ──
        corr_matrix = np.eye(K)
        for i in range(K):
            for j in range(i + 1, K):
                cc = self._canonical_correlation(
                    self.jacobians_[i], self.jacobians_[j]
                )
                corr_matrix[i, j] = cc
                corr_matrix[j, i] = cc

        # ── 4. Diversity index (effective number of views) ──
        # Based on eigenvalues of correlation matrix
        eigvals = np.linalg.eigvalsh(corr_matrix)
        eigvals = np.maximum(eigvals, 1e-10)
        p = eigvals / eigvals.sum()
        diversity_index = float(np.exp(-np.sum(p * np.log(p))))

        self.diversity_metrics_ = {
            'is_separating': is_separating,
            'stacked_rank': stacked_rank,
            'input_dim': m,
            'null_intersection_dim': null_dim,
            'per_operator': operator_reports,
            'pairwise_correlation': corr_matrix,
            'diversity_index': diversity_index,
        }
        return self.diversity_metrics_

    def summary(self):
        """Pretty-print diversity analysis."""
        if self.diversity_metrics_ is None:
            return "Not computed yet. Call compute() first."

        m = self.diversity_metrics_
        lines = [
            "╔══════════════════════════════════════════╗",
            "║  OPERATOR DIVERSITY ANALYSIS             ║",
            "╠══════════════════════════════════════════╣",
            f"║  Input dimension (m):       {m['input_dim']:>5d}        ║",
            f"║  Stacked Jacobian rank:     {m['stacked_rank']:>5d}        ║",
            f"║  Null intersection dim:     {m['null_intersection_dim']:>5d}        ║",
            f"║  Deviation-separating:      {'YES ✓' if m['is_separating'] else 'NO  ✗':>5s}        ║",
            f"║  Diversity index:           {m['diversity_index']:>5.2f}        ║",
            "╠══════════════════════════════════════════╣",
        ]
        for op in m['per_operator']:
            status = "FULL" if op['nullity'] == 0 else f"{op['nullity']}D blind"
            lines.append(
                f"║  {op['name']:12s}  rank={op['rank']}/{m['input_dim']}"
                f"  {status:>8s}  ║"
            )
        lines.append("╚══════════════════════════════════════════╝")
        return "\n".join(lines)

    def _numerical_jacobian(self, op, mu, m):
        """Estimate Jacobian DΦ(μ) via central differences with scaled eps."""
        x0 = mu.reshape(1, -1)
        y0 = op.transform(x0).ravel()
        d_out = len(y0)
        J = np.zeros((d_out, m))

        # Scale eps by feature magnitude for stability
        scale = np.abs(mu) + 1e-6

        for j in range(m):
            eps_j = self.eps * scale[j]
            x_plus = x0.copy()
            x_minus = x0.copy()
            x_plus[0, j] += eps_j
            x_minus[0, j] -= eps_j
            J[:, j] = (op.transform(x_plus).ravel() -
                        op.transform(x_minus).ravel()) / (2 * eps_j)
        return J

    @staticmethod
    def _canonical_correlation(J1, J2):
        """
        First canonical correlation between two operator Jacobians.
        Measures redundancy: 1.0 = identical views, 0.0 = orthogonal.
        """
        # Compute subspace angles
        _, _, Vt1 = np.linalg.svd(J1, full_matrices=False)
        _, _, Vt2 = np.linalg.svd(J2, full_matrices=False)
        r1 = min(J1.shape[0], J1.shape[1])
        r2 = min(J2.shape[0], J2.shape[1])
        V1 = Vt1[:r1].T
        V2 = Vt2[:r2].T
        # Cosine of principal angles
        M = V1.T @ V2
        cosines = np.linalg.svd(M, compute_uv=False)
        return float(cosines[0]) if len(cosines) > 0 else 0.0


# ═══════════════════════════════════════════════════════════════════
#  DEVIATION ENERGY — Per-Point Energy Scoring
# ═══════════════════════════════════════════════════════════════════

class DeviationEnergy:
    """
    Computes per-point energy from the deviation-induced functional:

      E(x) = (α/2)||R(x) − μ_R||²        ... radial
            + Σ_k (β_k/2)||Φ_k(x) − Φ_k(μ)||²  ... law deviation
            + (γ/2) Σ_j W(||x_i − x_j||)         ... interaction

    Normal points → low energy (near equilibrium).
    Anomalies → high energy (deviation in at least one law domain).

    Parameters
    ----------
    alpha : float
        Radial anchoring weight (centre attraction).
    beta_weights : str or ndarray
        How to set per-law weights β_k:
        - 'uniform': all equal (β_k = 1/K)
        - 'fisher': weight by Fisher discriminant ratio
        - 'adaptive': weight by per-law AUC discrimination
        - ndarray: explicit weights
    gamma : float
        Density interaction weight. 0 = disabled.
    interaction_kernel : str
        'gaussian': K(r) = -exp(-r²/σ²)  (attraction)
        'lennard_jones': K(r) = -1/r⁶ + λ/r¹²  (attract + repel)
        'log': K(r) = log(r + ε)
    use_mahalanobis : bool or 'auto'
        If True, use full Mahalanobis distance (captures cross-dim
        correlations in each law domain). If False, use diagonal
        (isotropic) distance. If 'auto', selects based on cross-law
        correlation: Mahalanobis when max |corr| > 0.6, else isotropic.
        Default False (isotropic is more robust on small datasets).
    sigma : float or 'auto'
        Bandwidth for Gaussian interaction kernel. If 'auto', uses
        median pairwise distance (adaptive bandwidth).
    """

    def __init__(self, alpha=1.0, beta_weights='uniform', gamma=0.0,
                 interaction_kernel='gaussian', sigma=1.0,
                 use_mahalanobis=False):
        self.alpha = alpha
        self.beta_weights = beta_weights
        self.gamma = gamma
        self.interaction_kernel = interaction_kernel
        self.sigma = sigma
        self.use_mahalanobis = use_mahalanobis

        # Fitted attributes
        self.mu_raw_ = None          # centroid in raw space
        self.mu_per_law_ = None      # centroid per law domain
        self.operators_ = None       # fitted operators
        self.beta_k_ = None          # per-law energy weights
        self._law_inv_cov_ = None    # per-law inverse covariance (Mahalanobis)
        self._raw_inv_cov_ = None    # raw-space inverse covariance
        self._fitted = False

    def fit(self, operators, X_ref, y_ref=None):
        """
        Fit energy model on reference (normal) data.

        Parameters
        ----------
        operators : list of (name, fitted_operator) tuples
        X_ref : ndarray (N, m)
            Normal reference data (raw features).
        y_ref : ndarray (N,) or None
            Labels for adaptive weight estimation.
        """
        self.operators_ = operators
        K = len(operators)

        # Use only normal data for centroid computation
        if y_ref is not None:
            X_normal = X_ref[y_ref == 0]
            if len(X_normal) == 0:
                X_normal = X_ref
        else:
            X_normal = X_ref

        self.mu_raw_ = X_normal.mean(axis=0)
        self._raw_std_ = X_normal.std(axis=0) + 1e-10

        # Raw-space inverse covariance (for Mahalanobis radial term)
        if self.use_mahalanobis:
            m = X_normal.shape[1]
            cov_raw = np.cov(X_normal.T) + 1e-4 * np.eye(m)
            self._raw_inv_cov_ = np.linalg.inv(cov_raw)
        else:
            self._raw_inv_cov_ = None

        # Compute per-law features, standardise within each law domain
        self.mu_per_law_ = []
        self._law_mu_ = []    # per-law mean (for standardisation)
        self._law_std_ = []   # per-law std  (for standardisation)
        self._law_inv_cov_ = []  # per-law inverse covariance (Mahalanobis)
        law_features = []     # full dataset (for adaptive weights)
        law_features_norm = []  # normal-only (for centroid)
        for name, op in operators:
            R_k = op.transform(X_ref)  # full dataset
            R_k_normal = op.transform(X_normal) if y_ref is not None else R_k

            # Per-law Z-standardisation (fitted on normal data)
            mu_k = R_k_normal.mean(axis=0)
            std_k = R_k_normal.std(axis=0) + 1e-10
            self._law_mu_.append(mu_k)
            self._law_std_.append(std_k)

            R_k_z = (R_k - mu_k) / std_k
            R_k_normal_z = (R_k_normal - mu_k) / std_k

            self.mu_per_law_.append(R_k_normal_z.mean(axis=0))  # ≈ 0
            law_features.append(R_k_z)
            law_features_norm.append(R_k_normal_z)

            # Per-law inverse covariance for Mahalanobis distance
            if self.use_mahalanobis:
                d_k = R_k_normal_z.shape[1]
                cov_k = np.cov(R_k_normal_z.T) + 1e-4 * np.eye(d_k)
                self._law_inv_cov_.append(np.linalg.inv(cov_k))
            else:
                self._law_inv_cov_.append(None)

        # Set beta weights
        if isinstance(self.beta_weights, np.ndarray):
            self.beta_k_ = self.beta_weights
        elif self.beta_weights == 'uniform':
            self.beta_k_ = np.ones(K) / K
        elif self.beta_weights == 'fisher' and y_ref is not None:
            self.beta_k_ = self._fisher_weights(law_features, y_ref)
        elif self.beta_weights == 'adaptive' and y_ref is not None:
            self.beta_k_ = self._adaptive_weights(law_features, y_ref)
        else:
            self.beta_k_ = np.ones(K) / K

        # Normalise beta so they sum to 1
        self.beta_k_ = self.beta_k_ / (self.beta_k_.sum() + 1e-10)

        # Store reference features for interaction term
        self._ref_features = np.hstack(law_features)
        self._ref_centroid = self._ref_features.mean(axis=0)

        self._fitted = True
        return self

    def score(self, X, return_components=False):
        """
        Compute per-point energy E(x_i).

        Parameters
        ----------
        X : ndarray (N, m)
            Data to score.
        return_components : bool
            If True, also return (E_radial, E_law, E_interaction).

        Returns
        -------
        energies : ndarray (N,)
            Total energy per point. Higher = more anomalous.
        """
        if not self._fitted:
            raise RuntimeError("Call fit() first")

        N = X.shape[0]

        # ── Component 1: Radial anchoring ──
        delta_raw = X - self.mu_raw_
        if self.use_mahalanobis and self._raw_inv_cov_ is not None:
            # Mahalanobis: δᵀ Σ⁻¹ δ (captures cross-feature correlations)
            E_radial = 0.5 * self.alpha * np.sum(
                delta_raw @ self._raw_inv_cov_ * delta_raw, axis=1
            )
        else:
            # Isotropic fallback: ||z||²
            delta_z = delta_raw / self._raw_std_
            E_radial = 0.5 * self.alpha * np.sum(delta_z ** 2, axis=1)

        # ── Component 2: Law deviation (per-law Mahalanobis) ──
        E_law = np.zeros(N)
        law_features = []
        for k, (name, op) in enumerate(self.operators_):
            R_k = op.transform(X)
            R_k_z = (R_k - self._law_mu_[k]) / self._law_std_[k]
            law_features.append(R_k_z)
            delta_k = R_k_z - self.mu_per_law_[k]
            if self.use_mahalanobis and self._law_inv_cov_[k] is not None:
                # Per-law Mahalanobis distance
                E_law += 0.5 * self.beta_k_[k] * np.sum(
                    delta_k @ self._law_inv_cov_[k] * delta_k, axis=1
                )
            else:
                E_law += 0.5 * self.beta_k_[k] * np.sum(delta_k ** 2, axis=1)

        # ── Component 3: Density interaction ──
        E_interaction = np.zeros(N)
        if self.gamma > 0 and N > 1:
            all_features = np.hstack(law_features)
            E_interaction = self._interaction_energy(all_features)

        E_total = E_radial + E_law + E_interaction

        if return_components:
            return E_total, E_radial, E_law, E_interaction
        return E_total

    def per_law_energy(self, X):
        """
        Decompose energy into per-law contributions.

        Returns
        -------
        law_energies : dict mapping law_name → ndarray (N,)
        """
        if not self._fitted:
            raise RuntimeError("Call fit() first")

        result = {}
        for k, (name, op) in enumerate(self.operators_):
            R_k = op.transform(X)
            R_k_z = (R_k - self._law_mu_[k]) / self._law_std_[k]
            delta_k = R_k_z - self.mu_per_law_[k]
            if self.use_mahalanobis and self._law_inv_cov_[k] is not None:
                result[name] = 0.5 * self.beta_k_[k] * np.sum(
                    delta_k @ self._law_inv_cov_[k] * delta_k, axis=1
                )
            else:
                result[name] = 0.5 * self.beta_k_[k] * np.sum(delta_k ** 2, axis=1)
        return result

    def energy_gradient(self, X):
        """
        Compute ∇E(x) — the deviation-induced force field.

        Uses numerical gradient (central differences).

        Returns
        -------
        grad : ndarray (N, m)
            Gradient vectors. Normal points → small gradient (near equilibrium).
            Anomalies → large gradient (strong restoring force).
        """
        N, m = X.shape
        eps = 1e-5
        grad = np.zeros((N, m))

        for j in range(m):
            X_plus = X.copy()
            X_minus = X.copy()
            X_plus[:, j] += eps
            X_minus[:, j] -= eps
            grad[:, j] = (self.score(X_plus) - self.score(X_minus)) / (2 * eps)

        return grad

    def gradient_magnitude(self, X):
        """
        ||∇E(x)|| — force magnitude. Anomalies have large gradient norms.
        Can be used as an additional anomaly score channel.
        """
        grad = self.energy_gradient(X)
        return np.linalg.norm(grad, axis=1)

    def _interaction_energy(self, features):
        """Compute pairwise interaction energy for each point.

        Uses adaptive bandwidth σ based on median pairwise distance
        to ensure the interaction term has meaningful magnitude relative
        to the radial and law terms. Subsamples for efficiency on large N.
        """
        N = features.shape[0]

        # Subsample for computational efficiency (O(N²) otherwise)
        max_n = min(N, 2000)
        if N > max_n:
            idx = np.random.RandomState(42).choice(N, max_n, replace=False)
            ref = features[idx]
        else:
            ref = features

        dists = cdist(features, ref, metric='euclidean')

        # Adaptive bandwidth: use median pairwise distance
        if self.sigma == 'auto' or self.sigma <= 0:
            sigma = np.median(dists[dists > 0]) + 1e-10
        else:
            sigma = self.sigma

        if self.interaction_kernel == 'gaussian':
            # Attractive Gaussian well
            K_vals = -np.exp(-dists ** 2 / (2 * sigma ** 2))
        elif self.interaction_kernel == 'lennard_jones':
            # Attract + repel: prevents collapse
            r = dists + 1e-6
            K_vals = -1.0 / (r ** 6) + 0.5 / (r ** 12)
        elif self.interaction_kernel == 'log':
            K_vals = np.log(dists + 1e-6)
        else:
            K_vals = -np.exp(-dists ** 2 / (2 * sigma ** 2))

        # Per-point: sum of interactions with all reference points
        E_int = self.gamma * 0.5 * K_vals.sum(axis=1) / max(ref.shape[0] - 1, 1)
        return E_int

    def _fisher_weights(self, law_features, y):
        """Weight laws by Fisher discriminant ratio."""
        K = len(law_features)
        ratios = np.zeros(K)
        for k, R_k in enumerate(law_features):
            mag = np.linalg.norm(R_k, axis=1)
            mu_0 = mag[y == 0].mean()
            mu_1 = mag[y == 1].mean()
            var_0 = mag[y == 0].var() + 1e-10
            var_1 = mag[y == 1].var() + 1e-10
            ratios[k] = (mu_1 - mu_0) ** 2 / (var_0 + var_1)
        return np.maximum(ratios, 0)

    def _adaptive_weights(self, law_features, y):
        """Weight laws by per-law aggregate AUC.

        Uses Mahalanobis distance within each law domain to capture
        synergistic signals across dimensions (not per-dimension screening
        which kills laws like rank where individual dims are weak but
        the aggregate ||z_k||² is strong).
        """
        from sklearn.metrics import roc_auc_score
        K = len(law_features)
        aucs = np.zeros(K)
        for k, R_k in enumerate(law_features):
            # Use Mahalanobis magnitude if available, else Euclidean
            if self.use_mahalanobis and self._law_inv_cov_[k] is not None:
                mu_k = self.mu_per_law_[k]
                delta = R_k - mu_k
                mag = np.sum(delta @ self._law_inv_cov_[k] * delta, axis=1)
            else:
                mag = np.sum(R_k ** 2, axis=1)
            try:
                auc = roc_auc_score(y, mag)
                aucs[k] = max(auc, 1 - auc)  # handle flipped polarity
            except ValueError:
                aucs[k] = 0.5
        # Convert AUC to weight: higher AUC → higher weight
        # Use softmax-like scheme for smoother weights (no hard zero)
        w = np.maximum(2 * (aucs - 0.5), 0.01)  # floor at 0.01
        return w


# ═══════════════════════════════════════════════════════════════════
#  ENERGY FLOW — Iterative Gradient-Flow Clustering (N-Body System)
# ═══════════════════════════════════════════════════════════════════

class EnergyFlow:
    """
    Deviation-induced potential flow in representation space.

    Implements the N-body dynamical system:
      x_i(t+1) = x_i(t) − η ∇E(x_i)

    where E combines:
      - Radial pull toward normal centroid
      - Law-weighted deviation contraction
      - Pairwise density interaction (attract similar, repel different)

    After convergence, normal points settle at stable equilibrium.
    Anomalies remain at high-energy positions.

    This unifies radial gravity, N-body attraction, law-weighted pull,
    and hypercube saturation into one coherent dynamical framework.

    Parameters
    ----------
    n_steps : int
        Number of gradient flow iterations.
    learning_rate : float
        Step size η for gradient descent.
    alpha : float
        Radial anchoring strength.
    gamma : float
        Pairwise interaction strength.
    interaction_kernel : str
        'attract_repel': Lennard-Jones style (prevents collapse)
        'gaussian': soft Gaussian attraction
    sigma : float
        Bandwidth for interaction kernel.
    convergence_tol : float
        Stop early if max displacement < tol.
    use_labels : bool
        If True and labels available, use class-conditional centroids
        (semi-supervised mode). If False, single-centroid (unsupervised).
    """

    def __init__(self, n_steps=10, learning_rate=0.05, alpha=1.0,
                 gamma=0.1, interaction_kernel='attract_repel',
                 sigma=1.0, convergence_tol=1e-6, use_labels=True):
        self.n_steps = n_steps
        self.learning_rate = learning_rate
        self.alpha = alpha
        self.gamma = gamma
        self.interaction_kernel = interaction_kernel
        self.sigma = sigma
        self.convergence_tol = convergence_tol
        self.use_labels = use_labels

        # Fitted
        self.mu_0_ = None
        self.mu_1_ = None
        self.operators_ = None
        self.mu_per_law_ = None
        self.beta_k_ = None
        self._energy_history = []
        self._fitted = False

    def fit(self, R, y, operators=None, operator_features=None):
        """
        Fit the energy flow system.

        Parameters
        ----------
        R : ndarray (N, D)
            Representation (post-stack or post-magnifier).
        y : ndarray (N,)
            Binary labels.
        operators : list of (name, operator) or None
            If provided, computes law-domain energy.
            If None, uses R directly as the representation.
        operator_features : list of ndarray or None
            Pre-computed per-law features (avoids re-transform).
        """
        self.mu_0_ = R[y == 0].mean(axis=0)
        self.mu_1_ = R[y == 1].mean(axis=0)
        self.mu_global_ = R.mean(axis=0)

        self.operators_ = operators
        if operator_features is not None:
            self.mu_per_law_ = [f[y == 0].mean(axis=0) for f in operator_features]
            K = len(operator_features)
            # Fisher weights on law features
            self.beta_k_ = np.ones(K) / K
            for k, feats in enumerate(operator_features):
                mag = np.linalg.norm(feats, axis=1)
                m0, m1 = mag[y == 0].mean(), mag[y == 1].mean()
                v0, v1 = mag[y == 0].var() + 1e-10, mag[y == 1].var() + 1e-10
                self.beta_k_[k] = (m1 - m0) ** 2 / (v0 + v1)
            self.beta_k_ = self.beta_k_ / (self.beta_k_.sum() + 1e-10)

        self._fitted = True
        return self

    def transform(self, R, y=None):
        """
        Apply energy flow to data points.

        Iteratively moves points under ẋ = −∇E until equilibrium.

        Parameters
        ----------
        R : ndarray (N, D)
        y : ndarray or None
            If provided (train), uses true labels for class centroids.
            If None (inference), assigns via nearest centroid.

        Returns
        -------
        R_flowed : ndarray (N, D)
            Positions after energy flow convergence.
        """
        if not self._fitted:
            raise RuntimeError("Call fit() first")

        R_w = R.copy().astype(np.float64)
        N, D = R_w.shape
        self._energy_history = []

        for step in range(self.n_steps):
            # ── Assign classes (if unlabelled) ──
            if y is not None:
                labels = y.astype(int)
            else:
                d0 = np.linalg.norm(R_w - self.mu_0_, axis=1)
                d1 = np.linalg.norm(R_w - self.mu_1_, axis=1)
                labels = (d1 < d0).astype(int)

            # ── Compute forces ──
            force = np.zeros_like(R_w)

            # Force 1: Radial pull toward own-class centroid
            mask_0 = (labels == 0)
            mask_1 = (labels == 1)
            if mask_0.any():
                force[mask_0] += self.alpha * (self.mu_0_ - R_w[mask_0])
            if mask_1.any():
                force[mask_1] += self.alpha * (self.mu_1_ - R_w[mask_1])

            # Force 2: Pairwise interaction
            if self.gamma > 0 and N > 1:
                force += self._interaction_force(R_w, labels)

            # ── Gradient step ──
            R_w += self.learning_rate * force

            # ── Track energy ──
            E = 0.5 * self.alpha * np.sum(
                np.where(
                    labels.reshape(-1, 1) == 0,
                    (R_w - self.mu_0_) ** 2,
                    (R_w - self.mu_1_) ** 2
                )
            )
            self._energy_history.append(float(E))

            # ── Convergence check ──
            max_disp = np.max(np.abs(self.learning_rate * force))
            if max_disp < self.convergence_tol:
                break

        return R_w

    def fit_transform(self, R, y, **kwargs):
        """Fit and transform in one call."""
        self.fit(R, y, **kwargs)
        return self.transform(R, y=y)

    def energy_per_point(self, R, y=None):
        """
        Compute final energy for each point (anomaly score).

        High energy = anomalous (far from equilibrium).
        """
        if y is not None:
            labels = y.astype(int)
        else:
            d0 = np.linalg.norm(R - self.mu_0_, axis=1)
            d1 = np.linalg.norm(R - self.mu_1_, axis=1)
            labels = (d1 < d0).astype(int)

        mu_assigned = np.where(
            labels.reshape(-1, 1) == 0,
            self.mu_0_,
            self.mu_1_
        )
        E = 0.5 * self.alpha * np.sum((R - mu_assigned) ** 2, axis=1)
        return E

    def convergence_report(self):
        """Return energy trajectory across flow steps."""
        if not self._energy_history:
            return "No flow computed yet."
        lines = ["Energy Flow Convergence:"]
        for i, e in enumerate(self._energy_history):
            bar = "█" * int(min(50, e / (self._energy_history[0] + 1e-10) * 50))
            lines.append(f"  Step {i:3d}: E = {e:10.2f}  {bar}")
        reduction = 1 - self._energy_history[-1] / (self._energy_history[0] + 1e-10)
        lines.append(f"  Energy reduction: {reduction*100:.1f}%")
        return "\n".join(lines)

    def _interaction_force(self, R, labels):
        """
        Compute pairwise interaction forces.

        Attract-repel kernel:
          Same class → attract (negative potential gradient)
          Different class → repel (positive potential gradient)
        """
        N = R.shape[0]
        force = np.zeros_like(R)

        # Subsample for O(N²) cost control
        max_interactions = 2000
        if N > max_interactions:
            indices = np.random.choice(N, max_interactions, replace=False)
            R_sub = R[indices]
            labels_sub = labels[indices]
        else:
            R_sub = R
            labels_sub = labels
            indices = np.arange(N)

        for i in range(len(R_sub)):
            delta = R_sub - R_sub[i]  # (n, D)
            dists = np.linalg.norm(delta, axis=1, keepdims=True) + 1e-8
            directions = delta / dists

            same_class = (labels_sub == labels_sub[i]).reshape(-1, 1)

            if self.interaction_kernel == 'attract_repel':
                # Same class: attract (soft spring)
                f_attract = self.gamma * directions / (1 + dists)
                # Different class: repel (inverse square)
                f_repel = -self.gamma * directions / (dists ** 2 + 0.1)
                f = np.where(same_class, f_attract, f_repel)
            elif self.interaction_kernel == 'gaussian':
                # Universal Gaussian attraction (weighted by similarity)
                w = np.exp(-dists ** 2 / (2 * self.sigma ** 2))
                f = self.gamma * w * directions
            else:
                f = np.zeros_like(delta)

            f[i] = 0  # no self-interaction

            # Map back to original indices if subsampled
            if N > max_interactions:
                force[indices[i]] += f.sum(axis=0)
            else:
                force[i] += f.sum(axis=0)

        return force / max(len(R_sub), 1)


# ═══════════════════════════════════════════════════════════════════
#  STABILITY ANALYSIS — Hessian & Basin Characterisation
# ═══════════════════════════════════════════════════════════════════

class StabilityAnalyser:
    """
    Analyses the energy functional's stability properties.

    Provides two complementary views:

    1. **Analytical radial stability**: The radial anchoring term
       E_rad = (α/2)||S(x−μ)||² has Hessian = αS²  ≻ 0 (always PD).
       This proves the centroid is a stable equilibrium of the radial potential.

    2. **Empirical class separation**: Computes energy gap between normal
       and anomalous classes. Higher separation → better detection.

    3. **Empirical Hessian** (optional): Full Hessian via finite differences
       at a reference point. Note: for nonlinear operators Φ_k, the raw-space
       centroid μ may NOT be the energy minimum due to Jensen's inequality
       (E[Φ_k(X)] ≠ Φ_k(E[X])). The empirical Hessian may therefore be
       indefinite even when the scoring works correctly.
    """

    def __init__(self, energy_scorer):
        """
        Parameters
        ----------
        energy_scorer : DeviationEnergy
            Fitted energy model.
        """
        self.energy = energy_scorer
        self.hessian_ = None
        self.eigenvalues_ = None
        self.eigenvectors_ = None

    def _compute_hessian(self, mu, eps=1e-3):
        """
        Compute Hessian at reference point via finite differences.

        Parameters
        ----------
        mu : ndarray (m,)
            Reference point (centroid).
        eps : float
            Step for finite differences. Larger values are more robust
            when operator transforms have large condition numbers.

        Returns
        -------
        report : dict
        """
        m = len(mu)
        H = np.zeros((m, m))

        # Scale eps by feature magnitude for numerical stability
        scale = np.abs(mu) + 1e-6
        eps_scaled = eps * scale

        E0 = self.energy.score(mu.reshape(1, -1))[0]

        for i in range(m):
            for j in range(i, m):
                ei = eps_scaled[i]
                ej = eps_scaled[j]
                if i == j:
                    x_p = mu.copy(); x_p[i] += ei
                    x_m = mu.copy(); x_m[i] -= ei
                    E_p = self.energy.score(x_p.reshape(1, -1))[0]
                    E_m = self.energy.score(x_m.reshape(1, -1))[0]
                    H[i, i] = (E_p - 2 * E0 + E_m) / (ei ** 2)
                else:
                    x_pp = mu.copy(); x_pp[i] += ei; x_pp[j] += ej
                    x_pm = mu.copy(); x_pm[i] += ei; x_pm[j] -= ej
                    x_mp = mu.copy(); x_mp[i] -= ei; x_mp[j] += ej
                    x_mm = mu.copy(); x_mm[i] -= ei; x_mm[j] -= ej
                    E_pp = self.energy.score(x_pp.reshape(1, -1))[0]
                    E_pm = self.energy.score(x_pm.reshape(1, -1))[0]
                    E_mp = self.energy.score(x_mp.reshape(1, -1))[0]
                    E_mm = self.energy.score(x_mm.reshape(1, -1))[0]
                    H[i, j] = H[j, i] = (E_pp - E_pm - E_mp + E_mm) / (4 * ei * ej)

        self.hessian_ = H
        self.eigenvalues_, self.eigenvectors_ = np.linalg.eigh(H)

        is_pd = bool(np.all(self.eigenvalues_ > 0))
        min_eigenvalue = float(self.eigenvalues_[0])
        max_eigenvalue = float(self.eigenvalues_[-1])
        condition = max_eigenvalue / (abs(min_eigenvalue) + 1e-15)

        return {
            'empirical_hessian_pd': is_pd,
            'min_eigenvalue': min_eigenvalue,
            'max_eigenvalue': max_eigenvalue,
            'condition_number': condition,
            'eigenvalues': self.eigenvalues_.tolist(),
            'n_unstable_directions': int(np.sum(self.eigenvalues_ < 0)),
        }

    def analyse(self, mu, X=None, y=None, eps=1e-3):
        """
        Full stability analysis combining analytical, empirical, and
        class-separation metrics.

        Parameters
        ----------
        mu : ndarray (m,)
            Reference point (centroid).
        X : ndarray (N, m), optional
            Data for class separation analysis.
        y : ndarray (N,), optional
            Labels (0=normal, 1=anomaly) for separation analysis.
        eps : float
            Step for finite differences in empirical Hessian.
        """
        report = {}

        # ── 1. Analytical radial stability ──
        # The radial term E_rad = (α/2)||S(x−μ)||² has diagonal Hessian
        # H_rad = α diag(1/σ_j²), which is always positive definite.
        alpha = self.energy.alpha
        raw_std = self.energy._raw_std_
        radial_hessian_diag = alpha / (raw_std ** 2)
        report['radial_hessian_pd'] = True  # always PD
        report['radial_min_eigenvalue'] = float(radial_hessian_diag.min())
        report['radial_max_eigenvalue'] = float(radial_hessian_diag.max())
        report['radial_condition'] = float(
            radial_hessian_diag.max() / (radial_hessian_diag.min() + 1e-15)
        )

        # ── 2. Class separation (if labels provided) ──
        if X is not None and y is not None:
            E_all = self.energy.score(X)
            E_normal = E_all[y == 0]
            E_anomaly = E_all[y == 1]
            if len(E_anomaly) > 0 and len(E_normal) > 0:
                report['energy_mean_normal'] = float(E_normal.mean())
                report['energy_mean_anomaly'] = float(E_anomaly.mean())
                report['energy_separation_ratio'] = float(
                    E_anomaly.mean() / (E_normal.mean() + 1e-15)
                )
                # Cohen's d effect size
                pooled_std = np.sqrt(
                    (E_normal.var() * len(E_normal) + E_anomaly.var() * len(E_anomaly))
                    / (len(E_normal) + len(E_anomaly))
                ) + 1e-10
                report['cohens_d'] = float(
                    (E_anomaly.mean() - E_normal.mean()) / pooled_std
                )

        # ── 3. Empirical Hessian at mu ──
        hessian_report = self._compute_hessian(mu, eps)
        report.update(hessian_report)

        # Overall stability assessment
        report['is_stable'] = (
            report['radial_hessian_pd']
            and report.get('energy_separation_ratio', 1.0) > 1.0
        )

        return report

    def summary(self, mu, X=None, y=None, eps=1e-3):
        """Pretty-print stability analysis."""
        report = self.analyse(mu, X=X, y=y, eps=eps)
        lines = [
            "╔══════════════════════════════════════════╗",
            "║  STABILITY ANALYSIS at μ                 ║",
            "╠══════════════════════════════════════════╣",
            f"║  Radial PD:    {'YES ✓' if report['radial_hessian_pd'] else 'NO  ✗':>6s}                   ║",
        ]
        if 'energy_separation_ratio' in report:
            lines.append(
                f"║  E(anom)/E(norm):  {report['energy_separation_ratio']:>8.2f}            ║"
            )
            lines.append(
                f"║  Cohen's d:       {report['cohens_d']:>8.2f}            ║"
            )
        lines += [
            f"║  Empirical PD:   {'YES ✓' if report['empirical_hessian_pd'] else 'NO  ✗':>6s}              ║",
            f"║  Stable:         {'YES ✓' if report['is_stable'] else 'NO  ✗':>6s}              ║",
            "╚══════════════════════════════════════════╝",
        ]
        return "\n".join(lines)
