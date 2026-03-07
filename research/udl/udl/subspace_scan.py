"""
Subspace Scan — Adaptive Random-Subspace Anomaly Scoring
=========================================================
Addresses the TYPE-1 BOUNDARY problem: missed anomalies have low global
displacement and no single lifted dimension is strong enough to trigger
detection. Their signal is DISTRIBUTED across many weak dimensions.

The fix: instead of scoring all D dimensions jointly (where the weak
signal drowns), we scan random LOW-dimensional subspace projections
and take the maximum score across projections.

Theory:
  If an anomaly's signal is spread across d_eff << D weak dimensions,
  a random k-dim projection (k ≈ 2–5) captures a fraction of that
  signal. Among N_proj random projections, at least one will align
  with the anomaly's "escape direction" — the subspace combination
  where the weak dims combine constructively.

  P(miss in all projections) ≈ (1 - d_eff/D)^(N_proj·k)

  For d_eff=5, D=50, k=3, N_proj=100:
    P(miss) ≈ (0.90)^300 ≈ 3.7e-14  — virtually guaranteed detection.

Algorithm:
  1. Fit N_proj random subspace projections (Gaussian or axis-aligned)
  2. In each subspace: compute Mahalanobis distance from normal centroid
  3. Final score = max over all projections (or soft-max)
  4. Optionally mix with magnifier score for global+local signal

The subspace scan is an MFLS-compatible strategy that can be plugged
into the MetaFusion pipeline as a new strategy entry.

Master-formula connection:
  miss(x) ← [δ_global(x) < θ_G] AND [∀j: disc_j(x) < θ_local]
  SubspaceScan breaks the second condition by computing:
    disc_subspace(x) = max_π ‖π(x) − π(μ_N)‖_Σ_π⁻¹
  Even when all disc_j are weak, disc_subspace can be large.
"""

import numpy as np
from sklearn.covariance import LedoitWolf


class SubspaceScanScorer:
    """
    Random subspace scanning for boundary-embedded anomaly detection.

    Instead of scoring all D dimensions at once, projects data into
    many random low-dimensional subspaces and takes the maximum
    Mahalanobis distance across projections. This catches anomalies
    whose signal is distributed across many individually weak dims.

    Parameters
    ----------
    n_projections : int
        Number of random subspace projections (default 200).
    subspace_dim : int or 'auto'
        Dimensionality of each random projection.
        'auto' picks min(max(3, D//10), 8).
    method : str
        'gaussian' — dense random normal projections
        'axis'     — axis-aligned random subsets (faster, interpretable)
        'mixed'    — 50% gaussian + 50% axis for diversity
    aggregation : str
        'max'     — max score across projections (catches rare directions)
        'softmax' — log-sum-exp (smooth max, less sensitive to noise)
        'top_k'   — mean of top-k projections (more robust)
    top_k : int
        Number of top projections to average when aggregation='top_k' (default 5).
    seed : int or None
        Random seed for reproducibility.
    boundary_boost : bool
        If True, additionally fits a boundary-zone detector that upweights
        samples close to the normal cloud (where TYPE-1 anomalies hide).
    boundary_quantile : float
        Percentile of normal Mahalanobis distances below which a sample
        is considered "in the boundary zone" (default 0.50).
    adaptive_stretch : bool
        If True, apply per-subspace adaptive stretching.  Each subspace gets
        its own steepness based on how discriminative it is:

        For weakly-discriminative subspaces (disc_j ≈ 0):
          k_j → γ_max  →  tanh amplifies subtle boundary differences
        For strongly-discriminative subspaces (disc_j ≈ 1):
          k_j → 0      →  score ≈ linear z, ranking fully preserved

        This is the INVERSE of the Magnifier's logic: the Magnifier saturates
        clear dims and silences blind dims.  Here we stretch weak subspaces
        (where the distributed boundary signal lives) and leave clear
        subspaces alone (so their ranking drives the max-aggregation).

        Formally:  score_j = disc_j · z_j + (1 − disc_j) · tanh(γ · z_j)
        where disc_j ∈ [0,1] is the subspace's discriminative score.
    stretch_gamma : float
        Maximum steepness of tanh for the weakest subspaces (default 3.0).
    """

    def __init__(self, n_projections=200, subspace_dim='auto',
                 method='mixed', aggregation='softmax', top_k=5,
                 seed=42, boundary_boost=True, boundary_quantile=0.50,
                 adaptive_stretch=True, stretch_gamma=3.0):
        self.n_projections = n_projections
        self.subspace_dim = subspace_dim
        self.method = method
        self.aggregation = aggregation
        self.top_k = top_k
        self.seed = seed
        self.boundary_boost = boundary_boost
        self.boundary_quantile = boundary_quantile
        self.adaptive_stretch = adaptive_stretch
        self.stretch_gamma = stretch_gamma

        # Fitted state
        self._projections = []        # list of (P, mu_sub, cov_inv_sub) tuples
        self._global_mu = None
        self._global_cov_inv = None
        self._boundary_thresh = None  # Mahal threshold for boundary zone
        self._sub_stats = []          # (μ_mahal, σ_mahal, disc_score) per projection
        self._fitted = False

    def fit(self, R, y):
        """
        Fit subspace projections on the representation space.

        Parameters
        ----------
        R : ndarray (N, D)
            Representation matrix (output of RepresentationStack).
        y : ndarray (N,)
            Labels (0=normal, 1=anomaly).

        Returns
        -------
        self
        """
        rng = np.random.RandomState(self.seed)
        N, D = R.shape
        mask_n = y == 0

        R_normal = R[mask_n]
        n_normal = R_normal.shape[0]

        # Auto-select subspace dimension
        if self.subspace_dim == 'auto':
            k = min(max(3, D // 10), 8)
        else:
            k = min(self.subspace_dim, D)

        # Global stats for boundary detection
        self._global_mu = R_normal.mean(axis=0)
        try:
            cov = LedoitWolf().fit(R_normal).covariance_
            self._global_cov_inv = np.linalg.pinv(cov + 1e-6 * np.eye(D))
        except Exception:
            self._global_cov_inv = np.eye(D) / (R_normal.var(axis=0).mean() + 1e-10)

        # Compute boundary threshold (on normal data)
        if self.boundary_boost:
            diffs = R_normal - self._global_mu
            global_mahal = np.sqrt(np.sum(diffs @ self._global_cov_inv * diffs, axis=1))
            self._boundary_thresh = np.percentile(global_mahal, self.boundary_quantile * 100)

        # Generate projections
        self._projections = []

        n_gauss = self.n_projections
        n_axis = 0
        if self.method == 'axis':
            n_gauss = 0
            n_axis = self.n_projections
        elif self.method == 'mixed':
            n_gauss = self.n_projections // 2
            n_axis = self.n_projections - n_gauss

        # Gaussian random projections
        for _ in range(n_gauss):
            P = rng.randn(D, k)
            # Orthogonalise for numerical stability
            P, _ = np.linalg.qr(P, mode='reduced')
            self._fit_one_projection(P, R_normal)

        # Axis-aligned random subsets
        for _ in range(n_axis):
            indices = rng.choice(D, size=k, replace=False)
            P = np.zeros((D, k))
            for j, idx in enumerate(indices):
                P[idx, j] = 1.0
            self._fit_one_projection(P, R_normal)

        # ── Compute per-subspace discriminative scores ──
        # For each subspace projection, measure how well it separates
        # normal from anomaly: Cohen's d on Mahalanobis distances.
        # disc_j = 0 → subspace is noise    → apply tanh stretch
        # disc_j = 1 → subspace is clear    → keep linear (preserve rank)
        self._sub_stats = []
        mask_a = y == 1
        R_anomaly = R[mask_a] if mask_a.any() else None

        for P, mu_sub, cov_inv_sub in self._projections:
            # Normal Mahalanobis in this subspace
            R_sub_n = R_normal @ P
            diffs_n = R_sub_n - mu_sub
            mahal_n = np.sqrt(np.sum(diffs_n @ cov_inv_sub * diffs_n, axis=1))
            mu_n = mahal_n.mean()
            sigma_n = mahal_n.std() + 1e-10

            # Discriminative score: how separated are anomalies?
            disc = 0.0
            if R_anomaly is not None and len(R_anomaly) >= 2:
                R_sub_a = R_anomaly @ P
                diffs_a = R_sub_a - mu_sub
                mahal_a = np.sqrt(np.sum(diffs_a @ cov_inv_sub * diffs_a, axis=1))
                mu_a = mahal_a.mean()
                sigma_a = mahal_a.std() + 1e-10

                # Cohen's d between normal and anomaly Mahalanobis distributions
                pooled_std = np.sqrt((sigma_n**2 + sigma_a**2) / 2)
                cohen_d = (mu_a - mu_n) / (pooled_std + 1e-10)
                cohen_d = max(cohen_d, 0.0)  # negative means anomalies closer → no signal

                # Per-subspace AUC (fast approximation via Mann-Whitney U)
                from scipy.stats import mannwhitneyu
                try:
                    u, _ = mannwhitneyu(mahal_a, mahal_n, alternative='greater')
                    sub_auc = u / (len(mahal_a) * len(mahal_n))
                except Exception:
                    sub_auc = 0.5

                # Composite discriminative score ∈ [0, 1]
                cd_norm = min(cohen_d, 3.0) / 3.0        # 0-1
                auc_norm = 2.0 * max(sub_auc - 0.5, 0)   # 0-1
                disc = 0.5 * cd_norm + 0.5 * auc_norm
                disc = min(disc, 1.0)

            self._sub_stats.append((mu_n, sigma_n, disc))

        self._fitted = True
        return self

    def _fit_one_projection(self, P, R_normal):
        """Fit a single subspace projection: compute normal stats in subspace."""
        R_sub = R_normal @ P  # (n_normal, k)
        mu_sub = R_sub.mean(axis=0)

        # Regularised covariance in subspace
        k = P.shape[1]
        n = R_sub.shape[0]
        if n > k + 2:
            try:
                cov_sub = LedoitWolf().fit(R_sub).covariance_
            except Exception:
                cov_sub = np.cov(R_sub, rowvar=False) + 1e-4 * np.eye(k)
        else:
            cov_sub = np.cov(R_sub, rowvar=False) + 1e-4 * np.eye(k)

        # Ensure positive definite
        cov_sub += 1e-6 * np.eye(k)

        try:
            cov_inv_sub = np.linalg.inv(cov_sub)
        except np.linalg.LinAlgError:
            cov_inv_sub = np.linalg.pinv(cov_sub)

        self._projections.append((P, mu_sub, cov_inv_sub))

    def score(self, R):
        """
        Score samples using max-over-subspace Mahalanobis distance.

        Parameters
        ----------
        R : ndarray (N, D)
            Representation matrix.

        Returns
        -------
        scores : ndarray (N,)  — higher = more anomalous
        """
        if not self._fitted:
            raise RuntimeError("SubspaceScanScorer not fitted. Call fit() first.")

        N = R.shape[0]
        all_scores = np.zeros((N, len(self._projections)))

        for j, (P, mu_sub, cov_inv_sub) in enumerate(self._projections):
            R_sub = R @ P        # (N, k)
            diffs = R_sub - mu_sub
            mahal = np.sqrt(np.sum(diffs @ cov_inv_sub * diffs, axis=1))

            # ── Adaptive per-subspace boundary stretching ──
            # Only WEAK subspaces (disc < 0.4) get tanh stretching.
            # Clear subspaces keep raw mahal to preserve distance ranking.
            #
            # Why? Z-scoring (mahal - mu_n)/sigma_n changes cross-subspace
            # ranking because sigma_n varies wildly. For clear subspaces
            # the original mahal ranking IS the correct ranking.
            #
            # Sigmoid gate:
            #   gate ≈ 1 for disc < 0.3 (weak → stretch hard)
            #   gate ≈ 0 for disc > 0.5 (clear → raw mahal)
            #   smooth transition at disc ≈ 0.4
            #
            #   score_j = (1 - gate) · mahal  +  gate · tanh(γ·z) · scale
            if self.adaptive_stretch and self._sub_stats:
                mu_n, sigma_n, disc_j = self._sub_stats[j]

                # Sigmoid gate: only stretch weak subspaces
                gate = 1.0 / (1.0 + np.exp(20.0 * (disc_j - 0.4)))

                if gate > 0.01:
                    # Z-score relative to normal distribution
                    z = (mahal - mu_n) / max(sigma_n, 1e-10)
                    z_pos = np.clip(z, 0.0, None)

                    # Tanh stretch: amplifies subtle boundary differences
                    stretched = np.tanh(self.stretch_gamma * z_pos)
                    # Scale back to approximate mahal magnitude
                    scale = max(mu_n + 2.0 * sigma_n, 1.0)
                    stretched = stretched * scale

                    # Blend: raw mahal + stretching for weak subspaces
                    score_j = (1.0 - gate) * mahal + gate * stretched
                    all_scores[:, j] = score_j
                else:
                    all_scores[:, j] = mahal   # clear subspace → raw
            else:
                all_scores[:, j] = mahal

        # Aggregate across projections
        if self.aggregation == 'max':
            scores = all_scores.max(axis=1)
        elif self.aggregation == 'softmax':
            # Log-sum-exp (smooth max) — numerically stable version
            temp = np.percentile(all_scores, 75)
            if temp < 1e-10:
                temp = 1.0
            scaled = all_scores / temp
            # Subtract max for numerical stability
            row_max = scaled.max(axis=1, keepdims=True)
            shifted = scaled - row_max
            scores = row_max.ravel() + np.log(np.mean(np.exp(shifted), axis=1))
            scores = temp * scores
        elif self.aggregation == 'top_k':
            k = min(self.top_k, all_scores.shape[1])
            # For each sample, take mean of top-k projection scores
            top_k_scores = np.sort(all_scores, axis=1)[:, -k:]
            scores = top_k_scores.mean(axis=1)
        else:
            scores = all_scores.max(axis=1)

        # Boundary boost: upweight samples in the boundary zone
        if self.boundary_boost and self._boundary_thresh is not None:
            diffs_g = R - self._global_mu
            global_mahal = np.sqrt(np.sum(
                diffs_g @ self._global_cov_inv * diffs_g, axis=1
            ))
            # Soft boundary weight: samples closer to the normal cloud
            # get a multiplicative boost to their subspace score.
            # This amplifies the signal for TYPE-1 boundary anomalies.
            boundary_weight = np.exp(
                -0.5 * (global_mahal / (self._boundary_thresh + 1e-10)) ** 2
            )
            # Combine: base subspace score + boundary-amplified score
            # The boundary boost adds 50% extra signal for boundary anomalies
            scores = scores * (1.0 + 0.5 * boundary_weight)

        return scores


class BoundaryRescueStrategy:
    """
    Wrapper that integrates SubspaceScanScorer as a UDL-compatible pipeline.

    This class implements the same fit(X, y) / score(X) interface as
    UDLPipeline, so it can be plugged directly into MetaFusion.

    It runs the standard representation stack, then applies SubspaceScan
    on the lifted representation. Optionally also runs the DimensionMagnifier
    for a hybrid score.

    Parameters
    ----------
    operators : list
        Spectrum operator specs (same format as UDLPipeline).
    n_projections : int
        Number of random subspace projections.
    subspace_dim : int or 'auto'
        Dimensionality of each projection.
    use_magnifier : bool
        If True, also fits DimensionMagnifier and blends scores.
    magnifier_weight : float
        Weight of magnifier score in the blend (0.0–1.0).
    """

    def __init__(self, operators, n_projections=200, subspace_dim='auto',
                 method='mixed', aggregation='softmax',
                 use_magnifier=True, magnifier_weight=0.3, seed=42):
        try:
            from .stack import RepresentationStack
        except ImportError:
            from udl.stack import RepresentationStack
        self.stack = RepresentationStack(operators=operators)
        self.scanner = SubspaceScanScorer(
            n_projections=n_projections,
            subspace_dim=subspace_dim,
            method=method,
            aggregation=aggregation,
            seed=seed,
            adaptive_stretch=True,   # Per-subspace adaptive stretching
            stretch_gamma=3.0,
        )
        self.use_magnifier = use_magnifier
        self.magnifier_weight = magnifier_weight
        self._magnifier = None
        self._fitted = False

    def fit(self, X, y):
        """Fit representation stack + subspace scanner (+ optional magnifier)."""
        X_ref = X[y == 0] if y is not None else X
        self.stack.fit(X_ref)
        R = self.stack.transform(X)

        # Fit subspace scanner
        self.scanner.fit(R, y)

        # Optional magnifier
        if self.use_magnifier:
            try:
                from .magnifier import DimensionMagnifier
            except ImportError:
                from magnifier import DimensionMagnifier
            self._magnifier = DimensionMagnifier(verbose=False)
            self._magnifier.fit(R, y,
                                law_names=self.stack.law_names_,
                                law_dims=self.stack.law_dims_)

        self._fitted = True
        return self

    def score(self, X):
        """Score via subspace scan, optionally blended with magnifier."""
        R = self.stack.transform(X)

        # Subspace scan score (with adaptive per-subspace stretching)
        scan_scores = self.scanner.score(R)

        # Normalise to [0, 1]
        s_min, s_max = scan_scores.min(), scan_scores.max()
        if s_max - s_min > 1e-10:
            scan_scores = (scan_scores - s_min) / (s_max - s_min)
        scan_scores = np.nan_to_num(scan_scores, nan=0.0, posinf=1.0, neginf=0.0)

        if self.use_magnifier and self._magnifier is not None:
            # Magnifier direct score (per-dim weighted z-scores)
            mag_scores = self._magnifier.score(R)
            m_min, m_max = mag_scores.min(), mag_scores.max()
            if m_max - m_min > 1e-10:
                mag_scores = (mag_scores - m_min) / (m_max - m_min)

            # Blend: magnifier catches clear-signal anomalies,
            # subspace scan (adaptively stretched) catches distributed-signal ones.
            w = self.magnifier_weight
            scores = (1 - w) * scan_scores + w * mag_scores
        else:
            scores = scan_scores

        return scores


class SubspaceMetaFusion:
    """
    Full meta-fusion with subspace scan as an additional strategy.

    Runs the standard MetaFusion strategies PLUS the SubspaceScan,
    then rank-fuses all of them. The subspace scan specifically
    targets TYPE-1 BOUNDARY anomalies that all standard strategies miss.

    Parameters
    ----------
    operators : list
        Spectrum operator specs.
    strategies : list of str
        Standard MetaFusion strategies to include.
    n_projections : int
        SubspaceScan projections.
    fusion_mode : str
        How to combine: 'mean', 'max', 'softmax'.
    """

    def __init__(self, operators=None, strategies=None,
                 n_projections=200, subspace_dim='auto',
                 fusion_mode='mean', verbose=True):
        import copy
        self.operators = operators
        self.strategies = strategies or ['fisher', 'fusion', 'quadsurf',
                                         'qs_expo', 'signed_lr', 'magnifier']
        self.n_projections = n_projections
        self.subspace_dim = subspace_dim
        self.fusion_mode = fusion_mode
        self.verbose = verbose

        self._meta = None
        self._boundary_rescue = None
        self._fitted = False

    def fit(self, X, y):
        """Fit MetaFusion + BoundaryRescue."""
        import copy
        try:
            from .meta_fusion import MetaFusionPipeline, default_operators
        except ImportError:
            from udl.meta_fusion import MetaFusionPipeline, default_operators

        ops = self.operators or default_operators()

        # Standard MetaFusion
        self._meta = MetaFusionPipeline(
            operators=copy.deepcopy(ops),
            strategies=self.strategies,
            fusion_mode=self.fusion_mode,
            verbose=self.verbose,
        )
        self._meta.fit(X, y)

        # Boundary rescue via subspace scan
        self._boundary_rescue = BoundaryRescueStrategy(
            operators=copy.deepcopy(ops),
            n_projections=self.n_projections,
            subspace_dim=self.subspace_dim,
            use_magnifier=True,
            magnifier_weight=0.3,
        )
        self._boundary_rescue.fit(X, y)

        self._fitted = True
        return self

    def score(self, X):
        """Rank-fuse MetaFusion + BoundaryRescue scores."""
        from scipy.stats import rankdata
        import numpy as np

        meta_scores = self._meta.score(X)
        rescue_scores = self._boundary_rescue.score(X)

        r_meta = rankdata(meta_scores, method='average')
        r_rescue = rankdata(rescue_scores, method='average')

        if self.fusion_mode == 'mean':
            # Weight: 60% meta (proven), 40% rescue (now strengthened by tanh)
            return 0.6 * r_meta + 0.4 * r_rescue
        elif self.fusion_mode == 'max':
            return np.maximum(r_meta, r_rescue)
        else:
            return 0.6 * r_meta + 0.4 * r_rescue
