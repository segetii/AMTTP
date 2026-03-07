"""
Deviation Layer — Theory-Grounded Second-Pass Scoring
======================================================
Turns the paper's error/deviation formulas (Theorems 1–4) into
computable features that augment the first-pass UDL representation.

**What this adds (the "error formulas"):**

1. Per-operator information matrices  I_k = DΦ_k(μ)ᵀ DΦ_k(μ)
2. SDP-optimal fusion weights         w* = argmax λ_min(Σ w_k I_k)
3. Theory-grounded composite score    S_w[x] = Σ w_k ||Φ_k(x) − Φ_k(μ)||
4. Quantitative deviation bound gap   gap_k = ||Φ_k(x)−Φ_k(μ)|| − (σ_min/√K)||x−μ||
5. Parallel/perpendicular decomposition relative to Fisher direction
6. Incidence angle (θ between deviation vector and normal-class axis)

Usage
-----
    layer2 = DeviationLayer()
    layer2.fit(stack, X_ref, y=y)             # computes Jacobians, info matrices, weights
    F = layer2.transform(stack, X)            # (N, n_features) second-layer features
    scores = layer2.score(stack, X)           # scalar theory score per point

Integration
-----------
    # As feature augmentation for a tree classifier:
    R_base = stack.transform(X)
    F_theory = layer2.transform(stack, X)
    X_aug = np.hstack([R_base, F_theory])     # feed to XGBoost/LightGBM

    # As standalone anomaly score:
    scores = layer2.score(stack, X)           # purely theory-driven

Reference: UDL Framework — Theorems 1–4 (universal_deviation_law.tex)
"""

import numpy as np
from scipy.optimize import minimize


class DeviationLayer:
    """
    Second computational layer implementing the paper's deviation theorems.

    Computes Jacobian-derived information matrices and optimal fusion
    weights from the fitted RepresentationStack, then produces
    theory-grounded anomaly features and scores.

    Parameters
    ----------
    perturbation_scale : float
        Step size for numerical Jacobian estimation (central differences).
    weight_method : str
        How to compute fusion weights:
        - 'sdp'   : maximize λ_min(Σ w_k I_k) — Theorem 4
        - 'trace' : w_k ∝ tr(I_k) — fast heuristic from Theorem 4
        - 'equal' : uniform 1/K
    n_fisher_dirs : int
        Number of Fisher/discriminant directions for parallel/perp
        decomposition (requires labels).
    """

    def __init__(self, perturbation_scale=1e-4, weight_method='sdp',
                 n_fisher_dirs=1):
        self.eps = perturbation_scale
        self.weight_method = weight_method
        self.n_fisher_dirs = n_fisher_dirs

        # Fitted state
        self.mu_raw_ = None          # raw-space centroid
        self.mu_per_op_ = None       # per-operator centroids in operator space
        self.jacobians_ = None       # list of J_k  (d_k × m)
        self.info_matrices_ = None   # list of I_k = J_k^T J_k  (m × m)
        self.stacked_jacobian_ = None
        self.sigma_min_ = None       # smallest singular value of stacked J
        self.weights_ = None         # optimal fusion weights (K,)
        self.K_ = None               # number of operators
        self.law_dims_ = None        # per-operator output dims
        self.law_names_ = None       # per-operator names
        self.fisher_dir_ = None      # Fisher discriminant direction (D,)
        self._op_std_ = None         # per-operator std for z-scoring
        self._fitted = False

    # ─────────────────────────────────────────────────────────────
    #  FIT
    # ─────────────────────────────────────────────────────────────

    def fit(self, stack, X_ref, y=None):
        """
        Compute Jacobians, information matrices, and optimal weights.

        Parameters
        ----------
        stack : RepresentationStack (fitted)
            The first-layer representation stack.
        X_ref : ndarray (N, m)
            Training data (raw features).
        y : ndarray (N,) or None
            Labels (0=normal, 1=anomaly) — used for Fisher direction.
        """
        # Reference centroid in raw space
        if y is not None:
            X_normal = X_ref[y == 0]
            if len(X_normal) == 0:
                X_normal = X_ref
        else:
            X_normal = X_ref

        self.mu_raw_ = X_normal.mean(axis=0)
        m = len(self.mu_raw_)
        self.K_ = len(stack.operators)
        self.law_dims_ = list(stack.law_dims_)
        self.law_names_ = list(stack.law_names_)

        # Standardize mu the same way the stack does
        if stack.standardize and stack._input_mu is not None:
            mu_std = (self.mu_raw_ - stack._input_mu) / stack._input_sigma
        else:
            mu_std = self.mu_raw_.copy()

        # ── 1. Numerical Jacobians at centroid ──
        self.jacobians_ = []
        self.mu_per_op_ = []

        for name, op in stack.operators:
            J = self._numerical_jacobian(op, mu_std, m)
            self.jacobians_.append(J)
            self.mu_per_op_.append(op.transform(mu_std.reshape(1, -1)).ravel())

        # ── 2. Stacked Jacobian and σ_min ──
        self.stacked_jacobian_ = np.vstack(self.jacobians_)
        U, S, Vt = np.linalg.svd(self.stacked_jacobian_, full_matrices=False)
        self.sigma_min_ = float(S[-1]) if len(S) > 0 else 0.0

        # ── 3. Per-operator information matrices I_k = J_k^T J_k ──
        self.info_matrices_ = []
        for J_k in self.jacobians_:
            I_k = J_k.T @ J_k
            self.info_matrices_.append(I_k)

        # ── 4. Optimal fusion weights (Theorem 4) ──
        self.weights_ = self._compute_weights()

        # ── 5. Per-operator std for z-scoring (fitted on normal data) ──
        R_normal = stack.transform(X_normal)
        self._op_std_ = []
        offset = 0
        for d_k in self.law_dims_:
            block = R_normal[:, offset:offset + d_k]
            self._op_std_.append(block.std(axis=0) + 1e-10)
            offset += d_k

        # ── 6. Fisher discriminant direction (if labels available) ──
        if y is not None and len(np.unique(y)) >= 2:
            R_all = stack.transform(X_ref)
            self.fisher_dir_ = self._compute_fisher_direction(R_all, y)
        else:
            self.fisher_dir_ = None

        self._fitted = True
        return self

    # ─────────────────────────────────────────────────────────────
    #  TRANSFORM — produce theory-grounded features
    # ─────────────────────────────────────────────────────────────

    def transform(self, stack, X):
        """
        Compute second-layer features from the deviation theorems.

        Returns an (N, F) matrix where F includes:
          - K weighted per-operator deviations   (K features)
          - composite score S_w                  (1 feature)
          - max-operator deviation               (1 feature)
          - deviation bound gap                  (1 feature)
          - deviation ratio (actual / bound)     (1 feature)
          - parallel projection (if Fisher)      (1 feature)
          - perpendicular magnitude (if Fisher)  (1 feature)
          - incidence angle θ (if Fisher)        (1 feature)
          - per-operator z-scored deviations     (K features)

        Parameters
        ----------
        stack : RepresentationStack (fitted)
        X : ndarray (N, m)

        Returns
        -------
        F : ndarray (N, n_features)
        """
        self._check_fitted()

        R = stack.transform(X)
        N = X.shape[0]

        # ── Per-operator deviation norms ──
        per_op_devs = self._per_operator_deviations(R)   # (N, K)

        # ── Weighted deviations ──
        weighted_devs = per_op_devs * self.weights_[np.newaxis, :]   # (N, K)

        # ── Composite score: S_w[x] = Σ_k w_k ||Φ_k(x) − Φ_k(μ)|| ──
        S_w = weighted_devs.sum(axis=1, keepdims=True)   # (N, 1)

        # ── Max-operator deviation ──
        max_dev = per_op_devs.max(axis=1, keepdims=True)  # (N, 1)

        # ── Raw-space distance ||x − μ|| ──
        raw_dist = np.linalg.norm(X - self.mu_raw_, axis=1)  # (N,)

        # ── Deviation bound from Theorem 1 ──
        #    max_k ||Φ_k(x) − Φ_k(μ)|| ≥ (σ_min / √K) · ||x − μ||
        bound = (self.sigma_min_ / np.sqrt(self.K_)) * raw_dist  # (N,)

        # Gap: how much the actual max deviation exceeds the bound
        gap = max_dev.ravel() - bound                     # (N,)
        gap = np.maximum(gap, 0)                          # non-negative

        # Ratio: actual / bound (>1 means anomaly is "amplified")
        ratio = max_dev.ravel() / (bound + 1e-10)         # (N,)

        # ── Z-scored per-operator deviations ──
        z_devs = self._per_operator_z_deviations(R)       # (N, K)

        # ── Parallel/perpendicular decomposition ──
        if self.fisher_dir_ is not None:
            proj_parallel, proj_perp, angle = self._fisher_decompose(R)
        else:
            proj_parallel = np.zeros((N, 1))
            proj_perp = np.zeros((N, 1))
            angle = np.zeros((N, 1))

        # ── Assemble feature matrix ──
        features = np.hstack([
            weighted_devs,                    # K features
            S_w,                              # 1
            max_dev,                          # 1
            gap.reshape(-1, 1),               # 1
            ratio.reshape(-1, 1),             # 1
            z_devs,                           # K features
            proj_parallel,                    # 1
            proj_perp,                        # 1
            angle,                            # 1
        ])
        return features

    def feature_names(self):
        """Return human-readable names for each output feature."""
        names = []
        for name in self.law_names_:
            names.append(f"wdev_{name}")
        names += ["S_w_composite", "max_deviation", "bound_gap", "bound_ratio"]
        for name in self.law_names_:
            names.append(f"zdev_{name}")
        names += ["fisher_parallel", "fisher_perp", "incidence_angle"]
        return names

    # ─────────────────────────────────────────────────────────────
    #  SCORE — standalone theory-driven anomaly score
    # ─────────────────────────────────────────────────────────────

    def score(self, stack, X):
        """
        Compute a single theory-grounded anomaly score per point.

        Combines the SDP-weighted composite score with the deviation
        bound ratio (how much actual deviation exceeds the theorem bound).

        Returns
        -------
        scores : ndarray (N,)
        """
        self._check_fitted()

        R = stack.transform(X)
        per_op_devs = self._per_operator_deviations(R)

        # SDP-weighted composite
        S_w = (per_op_devs * self.weights_).sum(axis=1)

        # Deviation bound ratio
        raw_dist = np.linalg.norm(X - self.mu_raw_, axis=1)
        bound = (self.sigma_min_ / np.sqrt(self.K_)) * raw_dist
        max_dev = per_op_devs.max(axis=1)
        ratio = max_dev / (bound + 1e-10)

        # Combined: geometric mean of composite and ratio
        # This rewards both high aggregate deviation AND exceeding the bound
        score = np.sqrt(S_w * ratio)

        return score

    def summary(self):
        """Pretty-print the deviation layer configuration."""
        if not self._fitted:
            return "Not fitted yet."

        lines = [
            "╔══════════════════════════════════════════════╗",
            "║  DEVIATION LAYER — Theory Second Pass        ║",
            "╠══════════════════════════════════════════════╣",
            f"║  Operators (K):        {self.K_:>5d}                ║",
            f"║  σ_min (stacked J):    {self.sigma_min_:>8.4f}             ║",
            f"║  Bound factor σ/√K:    {self.sigma_min_/np.sqrt(self.K_):>8.4f}             ║",
            f"║  Weight method:        {self.weight_method:>8s}             ║",
            "╠══════════════════════════════════════════════╣",
            "║  Per-Operator Weights (Theorem 4):           ║",
        ]
        for i, name in enumerate(self.law_names_):
            w = self.weights_[i]
            tr = np.trace(self.info_matrices_[i])
            lines.append(
                f"║   {name:12s}  w={w:.4f}  tr(I_k)={tr:>10.2f}  ║"
            )

        # Worst-case sensitivity
        I_weighted = sum(w * I for w, I in zip(self.weights_, self.info_matrices_))
        eta = float(np.linalg.eigvalsh(I_weighted)[0])
        lines.append("╠══════════════════════════════════════════════╣")
        lines.append(f"║  η(w*) = λ_min(Σ w_k I_k): {eta:>10.4f}       ║")
        lines.append("╚══════════════════════════════════════════════╝")
        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────
    #  INTERNAL METHODS
    # ─────────────────────────────────────────────────────────────

    def _per_operator_deviations(self, R):
        """
        Compute ||Φ_k(x) − Φ_k(μ)|| for each operator k.

        Parameters
        ----------
        R : ndarray (N, D)
            Full representation (concatenated operator outputs).

        Returns
        -------
        devs : ndarray (N, K)
        """
        N = R.shape[0]
        devs = np.zeros((N, self.K_))
        offset = 0
        for k, d_k in enumerate(self.law_dims_):
            block = R[:, offset:offset + d_k]           # (N, d_k)
            delta = block - self.mu_per_op_[k]           # (N, d_k)
            devs[:, k] = np.linalg.norm(delta, axis=1)   # (N,)
            offset += d_k
        return devs

    def _per_operator_z_deviations(self, R):
        """
        Z-score normalised per-operator deviation magnitudes.
        Each operator's deviations are divided by their normal-class std.
        """
        N = R.shape[0]
        z_devs = np.zeros((N, self.K_))
        offset = 0
        for k, d_k in enumerate(self.law_dims_):
            block = R[:, offset:offset + d_k]
            delta = block - self.mu_per_op_[k]
            # Divide each dimension by its std, then take norm
            z_delta = delta / self._op_std_[k]
            z_devs[:, k] = np.linalg.norm(z_delta, axis=1)
            offset += d_k
        return z_devs

    def _compute_weights(self):
        """
        Compute optimal fusion weights w ∈ Δ_K (Theorem 4).

        Maximizes η(w) = λ_min(Σ_k w_k I_k) over the simplex.
        """
        K = self.K_
        if K == 1:
            return np.array([1.0])

        if self.weight_method == 'equal':
            return np.ones(K) / K

        if self.weight_method == 'trace':
            # Heuristic: w_k ∝ tr(I_k)
            traces = np.array([np.trace(I) for I in self.info_matrices_])
            traces = np.maximum(traces, 1e-10)
            return traces / traces.sum()

        # ── SDP method: max λ_min(Σ w_k I_k) over simplex Δ_K ──
        # We solve: min -λ_min(Σ w_k I_k)
        # This is a concave maximization on the simplex — use
        # sequential eigenvalue iteration (no SDP solver needed).

        m = self.info_matrices_[0].shape[0]

        def neg_eta(w):
            """Negative worst-case sensitivity."""
            I_w = np.zeros((m, m))
            for k in range(K):
                I_w += w[k] * self.info_matrices_[k]
            return -float(np.linalg.eigvalsh(I_w)[0])

        def neg_eta_grad(w):
            """Gradient of -λ_min via perturbation theory."""
            I_w = np.zeros((m, m))
            for k in range(K):
                I_w += w[k] * self.info_matrices_[k]
            eigvals, eigvecs = np.linalg.eigh(I_w)
            v_min = eigvecs[:, 0]  # eigenvector for λ_min
            # ∂λ_min/∂w_k = v_min^T I_k v_min
            grad = np.array([
                -float(v_min @ self.info_matrices_[k] @ v_min)
                for k in range(K)
            ])
            return grad

        # Initial point: trace heuristic
        traces = np.array([np.trace(I) for I in self.info_matrices_])
        traces = np.maximum(traces, 1e-10)
        w0 = traces / traces.sum()

        # Simplex constraints
        constraints = [{'type': 'eq', 'fun': lambda w: w.sum() - 1.0}]
        bounds = [(1e-6, 1.0)] * K

        try:
            result = minimize(
                neg_eta, w0, jac=neg_eta_grad,
                method='SLSQP', bounds=bounds, constraints=constraints,
                options={'maxiter': 200, 'ftol': 1e-10}
            )
            w_opt = result.x
            w_opt = np.maximum(w_opt, 0)
            w_opt /= w_opt.sum()
        except Exception:
            # Fallback to trace heuristic
            w_opt = w0

        return w_opt

    def _numerical_jacobian(self, op, mu, m):
        """
        Estimate Jacobian DΦ(μ) via central finite differences.
        Scales perturbation by feature magnitude for numerical stability.
        """
        x0 = mu.reshape(1, -1)
        y0 = op.transform(x0).ravel()
        d_out = len(y0)
        J = np.zeros((d_out, m))

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

    def _compute_fisher_direction(self, R, y):
        """
        Compute Fisher LDA direction in representation space.
        w_F = S_w^{-1} (μ_1 − μ_0) where S_w is within-class scatter.
        """
        R0 = R[y == 0]
        R1 = R[y == 1]
        if len(R0) < 2 or len(R1) < 2:
            return None

        mu0 = R0.mean(axis=0)
        mu1 = R1.mean(axis=0)
        diff = mu1 - mu0

        # Within-class scatter (regularized)
        S0 = np.cov(R0.T) if R0.shape[0] > R0.shape[1] else np.eye(R.shape[1]) * 0.01
        S1 = np.cov(R1.T) if R1.shape[0] > R1.shape[1] else np.eye(R.shape[1]) * 0.01
        n0, n1 = len(R0), len(R1)
        S_w = ((n0 - 1) * S0 + (n1 - 1) * S1) / (n0 + n1 - 2)

        # Regularize
        S_w += 1e-4 * np.eye(S_w.shape[0])

        try:
            w_F = np.linalg.solve(S_w, diff)
        except np.linalg.LinAlgError:
            w_F = diff  # fallback

        # Normalize
        norm = np.linalg.norm(w_F)
        if norm > 1e-10:
            w_F /= norm

        return w_F

    def _fisher_decompose(self, R):
        """
        Decompose representation into components parallel and
        perpendicular to the Fisher discriminant direction.

        Returns
        -------
        parallel : ndarray (N, 1)
            Projection onto Fisher direction.
        perp_mag : ndarray (N, 1)
            Magnitude of perpendicular component.
        angle : ndarray (N, 1)
            Incidence angle θ ∈ [0, π/2] between deviation vector
            and Fisher direction.
        """
        w = self.fisher_dir_
        if w is None:
            N = R.shape[0]
            return np.zeros((N, 1)), np.zeros((N, 1)), np.zeros((N, 1))

        # Deviation vectors from centroid-in-R-space
        mu_R = np.concatenate(self.mu_per_op_)
        delta = R - mu_R                              # (N, D)

        # Parallel component: (δ · w_F)
        proj = delta @ w                               # (N,)

        # Perpendicular: ||δ - (δ·w)w||
        parallel_vec = proj[:, np.newaxis] * w         # (N, D)
        perp_vec = delta - parallel_vec                # (N, D)
        perp_mag = np.linalg.norm(perp_vec, axis=1)   # (N,)

        # Incidence angle: cos(θ) = |δ·w| / ||δ||
        delta_norm = np.linalg.norm(delta, axis=1) + 1e-10
        cos_theta = np.abs(proj) / delta_norm
        cos_theta = np.clip(cos_theta, 0, 1)
        angle = np.arccos(cos_theta)                   # [0, π/2]

        return (proj.reshape(-1, 1),
                perp_mag.reshape(-1, 1),
                angle.reshape(-1, 1))

    def _check_fitted(self):
        if not self._fitted:
            raise RuntimeError("DeviationLayer not fitted. Call fit() first.")
