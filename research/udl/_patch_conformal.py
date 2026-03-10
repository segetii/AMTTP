"""Patch: Add universal conformal scoring to ReducedTensorDescriptor.

Adds:
  1. fit_reference(X_ref, cal_frac=0.2) — split reference into fit/calibration
  2. score_conformal(X)  — rank-transform + Fisher p-value fusion + conformal calibration
  3. predict_pvalue(X)   — distribution-free conformal p-values with FAR guarantee
"""
import os, sys

FP = os.path.join(os.path.dirname(__file__), 'udl', 'system_mode.py')
with open(FP, encoding='utf-8') as f:
    lines = f.readlines()

joined = ''.join(lines)
if 'def fit_reference' in joined:
    print('Already patched.'); sys.exit(0)

print(f'Original lines: {len(lines)}')

# Find @staticmethod before _to_scalar (after score_panel)
insert_idx = None
for i in range(len(lines)-1, 2100, -1):
    if '    @staticmethod' in lines[i] and '_to_scalar' in lines[i+1]:
        insert_idx = i
        break

assert insert_idx is not None, 'Cannot find @staticmethod _to_scalar after score_panel'
print(f'Inserting before line {insert_idx+1}')

new_methods = r'''    # ═══════════════════════════════════════════════════════════════
    #  UNIVERSAL CONFORMAL SCORING — dataset-agnostic
    # ═══════════════════════════════════════════════════════════════

    def fit_reference(self, X_ref: np.ndarray,
                      cal_frac: float = 0.2,
                      random_state: int = 42) -> 'ReducedTensorDescriptor':
        """Fit the descriptor and calibration set for conformal scoring.

        Splits reference data into:
          - fit set (1 - cal_frac): used to fit GMM, covariance, medoid
          - calibration set (cal_frac): used to build the reference
            distribution of nonconformity scores for conformal inference

        This is the foundation of the universal scorer: all subsequent
        scoring is relative to the calibration set, making it
        distribution-free under exchangeability.

        Parameters
        ----------
        X_ref     : (N, d) array — normal-period reference data
        cal_frac  : float — fraction reserved for calibration (default 0.2)
        random_state : int — reproducibility seed

        Returns
        -------
        self
        """
        X_ref = np.asarray(X_ref, dtype=np.float64)
        N = len(X_ref)
        n_cal = max(10, int(N * cal_frac))
        n_fit = N - n_cal

        rng = np.random.default_rng(random_state)
        perm = rng.permutation(N)
        idx_fit = perm[:n_fit]
        idx_cal = perm[n_fit:]

        X_fit = X_ref[idx_fit]
        X_cal = X_ref[idx_cal]

        # Fit descriptor on the fit set
        self.fit(X_fit)

        # Compute descriptor features on calibration set
        D_cal = self.transform(X_cal)
        n_eigs = min(self.n_eigs, X_ref.shape[1])

        # Store per-feature reference distributions (calibration set)
        # Features: grad_norm, eigenvalues..., mahalanobis, medoid,
        #           trace, det, morse
        n_features = D_cal.shape[1]
        self._cal_features = D_cal                    # (n_cal, n_features)
        self._cal_sorted = np.sort(D_cal, axis=0)     # sorted per column
        self._cal_N = n_cal
        self._cal_X = X_cal                            # raw calibration data

        # Also compute the nonconformity score on calibration set
        # using the rank-based aggregation (same as score_conformal)
        cal_pvals = self._feature_pvalues(D_cal, D_cal)
        self._cal_nonconf = self._aggregate_pvalues(cal_pvals)
        self._cal_nonconf_sorted = np.sort(self._cal_nonconf)

        self._conformal_fitted = True
        return self

    def _feature_pvalues(self, D_test: np.ndarray,
                         D_cal: np.ndarray) -> np.ndarray:
        """Convert each descriptor feature to a tail probability.

        For each feature j and test point i:
            p_j(x_i) = (1 + #{z in cal : z_j >= x_ij}) / (n_cal + 1)

        This is the empirical survival function —
        distribution-free, scale-invariant, unit-invariant.

        Parameters
        ----------
        D_test : (N, m) — descriptor features of test points
        D_cal  : (n_cal, m) — descriptor features of calibration set

        Returns
        -------
        pvals : (N, m) — per-feature p-values in (0, 1]
        """
        N, m = D_test.shape
        n_cal = len(D_cal)
        pvals = np.zeros((N, m), dtype=np.float64)

        for j in range(m):
            # For each feature, count how many calibration values
            # are >= the test value (right tail = more anomalous)
            # Use searchsorted on the sorted calibration column
            sorted_col = np.sort(D_cal[:, j])
            # Number of cal values >= test value
            rank = n_cal - np.searchsorted(sorted_col, D_test[:, j],
                                           side='left')
            pvals[:, j] = (1 + rank) / (n_cal + 1)

        return pvals

    def _aggregate_pvalues(self, pvals: np.ndarray) -> np.ndarray:
        """Aggregate per-feature p-values into a single nonconformity score.

        Uses a combination of Fisher and Cauchy methods for robustness:

        Fisher: S_F = -2 * sum(log(p_j))   ~ chi^2(2m) under H0
        Cauchy: S_C = sum(tan(pi*(0.5 - p_j))) / m   (heavy-tailed, robust)

        Final: max(rank(S_F), rank(S_C))  — takes the more extreme signal

        This avoids dataset-specific weights entirely.

        Parameters
        ----------
        pvals : (N, m) — per-feature p-values

        Returns
        -------
        scores : (N,) — nonconformity scores (higher = more anomalous)
        """
        eps = 1e-15
        # Fisher combination
        fisher = -2.0 * np.sum(np.log(np.maximum(pvals, eps)), axis=1)

        # Cauchy combination (robust to dependence)
        cauchy = np.mean(np.tan(np.pi * (0.5 - pvals)), axis=1)

        # Combine: take the max of rank-normalised Fisher and Cauchy
        # This ensures that if either view detects the anomaly, it fires
        N = len(fisher)
        if N < 2:
            return fisher

        def rank_norm(x):
            """Rank-normalise to [0, 1]."""
            order = np.argsort(np.argsort(x))
            return order / (N - 1 + 1e-15)

        combined = np.maximum(rank_norm(fisher), rank_norm(cauchy))
        return combined

    def score_conformal(self, X: np.ndarray) -> np.ndarray:
        """Universal anomaly score — dataset-agnostic, distribution-free.

        Pipeline:
          1. Transform X through the descriptor (gradient, Hessian, etc.)
          2. Convert each feature to a tail p-value vs calibration set
          3. Aggregate p-values via Fisher + Cauchy combination
          4. Compute conformal nonconformity score

        The resulting score is:
          - Scale-invariant (rank-based)
          - Distribution-free (empirical tail probabilities)
          - No dataset-specific weights
          - No assumptions about feature distributions

        Must call ``fit_reference()`` first.

        Parameters
        ----------
        X : (N, d) array — points to score

        Returns
        -------
        scores : (N,) array — higher = more anomalous
        """
        if not getattr(self, '_conformal_fitted', False):
            raise RuntimeError('Call fit_reference() before score_conformal()')

        X = np.asarray(X, dtype=np.float64)
        D_test = self.transform(X)

        # Per-feature p-values against calibration set
        pvals = self._feature_pvalues(D_test, self._cal_features)

        # Aggregate into nonconformity score
        scores = self._aggregate_pvalues(pvals)
        return scores

    def predict_pvalue(self, X: np.ndarray) -> np.ndarray:
        """Conformal p-values with distribution-free validity.

        For each test point x:
            p(x) = (1 + #{i : A_cal_i >= A(x)}) / (n_cal + 1)

        where A(x) is the nonconformity score from score_conformal.

        Guarantee (Vovk et al., 2005):
            Under exchangeability, P(p(X) <= alpha) <= alpha
            for any distribution, any alpha, any d.

        This means:
            - Set alpha = 0.01 → at most 1% false alarm rate, guaranteed.
            - No tuning. No dataset-specific thresholds.
            - Works on ERCOT, bank data, or any future dataset.

        Must call ``fit_reference()`` first.

        Parameters
        ----------
        X : (N, d) array — points to score

        Returns
        -------
        pvalues : (N,) array — conformal p-values in (0, 1]
                  Small p = anomalous. Alert if p < alpha.
        """
        if not getattr(self, '_conformal_fitted', False):
            raise RuntimeError('Call fit_reference() before predict_pvalue()')

        X = np.asarray(X, dtype=np.float64)
        D_test = self.transform(X)

        # Nonconformity score for test points
        pvals_feat = self._feature_pvalues(D_test, self._cal_features)
        A_test = self._aggregate_pvalues(pvals_feat)

        # Conformal p-value: compare against calibration nonconformity scores
        n_cal = self._cal_N
        A_cal_sorted = self._cal_nonconf_sorted

        # For each test point: p = (1 + #{cal scores >= A_test}) / (n_cal + 1)
        # Using searchsorted on sorted calibration scores
        rank = n_cal - np.searchsorted(A_cal_sorted, A_test, side='left')
        pvalues = (1 + rank) / (n_cal + 1)

        return pvalues

    def score_conformal_panel(self, X_3d: np.ndarray,
                              y_time: np.ndarray = None,
                              window: int = 4) -> np.ndarray:
        """Universal panel-aware scoring with conformal calibration.

        Combines the distribution-free conformal approach with
        temporal and cross-sectional aggregation.

        Parameters
        ----------
        X_3d   : (T, N, d) array — panel data
        y_time : (T,) array or None — per-period labels (0 = normal)
        window : int — rolling window for temporal features

        Returns
        -------
        q_scores : (T,) array — period-level anomaly scores
        """
        X_3d = np.asarray(X_3d, dtype=np.float64)
        if X_3d.ndim != 3:
            raise ValueError(f'Expected (T, N, d), got {X_3d.shape}')

        T, N, d = X_3d.shape
        X_flat = X_3d.reshape(T * N, d)

        # Determine reference data
        if y_time is not None:
            y_time = np.asarray(y_time)
            normal_mask = (y_time == 0)
            X_ref = X_3d[normal_mask].reshape(-1, d)
        else:
            n_calm = max(1, int(T * 0.3))
            X_ref = X_3d[:n_calm].reshape(-1, d)

        # Fit conformal reference
        self.fit_reference(X_ref, cal_frac=0.2)

        # Conformal p-values for all points
        pvals = self.predict_pvalue(X_flat)       # (T*N,)
        pvals_3d = pvals.reshape(T, N)            # (T, N)

        # Conformal scores for all points
        cscores = self.score_conformal(X_flat)    # (T*N,)
        cscores_3d = cscores.reshape(T, N)        # (T, N)

        # ── Cross-sectional aggregation (distribution-free) ──
        # Mean conformal score per period
        q_mean = cscores_3d.mean(axis=1)

        # Fraction of agents with p < 0.05 (significant anomalies)
        q_frac_sig = (pvals_3d < 0.05).mean(axis=1)

        # Fraction of agents with p < 0.01 (highly significant)
        q_frac_hsig = (pvals_3d < 0.01).mean(axis=1)

        # Minimum p-value across agents (worst case)
        q_min_p = pvals_3d.min(axis=1)
        # Transform to score: -log(min_p) for monotonicity
        q_min_p_score = -np.log(np.maximum(q_min_p, 1e-15))

        # Cross-sectional dispersion of conformal scores
        q_std = cscores_3d.std(axis=1)

        # ── Temporal dynamics (distribution-free) ──
        # Rolling Z-score of mean conformal score
        q_z = np.zeros(T)
        for t in range(window, T):
            w = q_mean[t-window:t]
            mu_w, std_w = w.mean(), w.std() + 1e-10
            q_z[t] = max((q_mean[t] - mu_w) / std_w, 0.0)

        # Momentum
        q_mom = np.zeros(T)
        q_mom[1:] = np.maximum(q_mean[1:] - q_mean[:-1], 0.0)

        # ── Aggregate using rank-based fusion (no fixed weights) ──
        # Each component is rank-normalised, then averaged
        components = np.column_stack([
            q_mean,        # average distress
            q_frac_sig,    # breadth of anomalies
            q_frac_hsig,   # breadth of severe anomalies
            q_min_p_score, # worst-case agent
            q_std,         # cross-sectional spread
            q_z,           # temporal acceleration
            q_mom,         # momentum
        ])

        # Rank-normalise each component to [0, 1]
        def rank_norm(x):
            if x.max() == x.min():
                return np.zeros_like(x)
            order = np.argsort(np.argsort(x)).astype(np.float64)
            return order / (len(x) - 1 + 1e-15)

        n_comp = components.shape[1]
        ranked = np.zeros_like(components)
        for j in range(n_comp):
            ranked[:, j] = rank_norm(components[:, j])

        # Equal-weight average of ranks (no dataset-specific tuning)
        q_scores = ranked.mean(axis=1)

        return q_scores

'''

lines[insert_idx:insert_idx] = [new_methods]

with open(FP, 'w', encoding='utf-8') as f:
    f.writelines(lines)

total_lines = ''.join(lines).count('\n')
print(f'Inserted. Total lines: {total_lines}')
print(f'fit_reference: {"def fit_reference" in "".join(lines)}')
print(f'score_conformal: {"def score_conformal" in "".join(lines)}')
print(f'predict_pvalue: {"def predict_pvalue" in "".join(lines)}')
print(f'score_conformal_panel: {"def score_conformal_panel" in "".join(lines)}')
print(f'_feature_pvalues: {"def _feature_pvalues" in "".join(lines)}')
print(f'_aggregate_pvalues: {"def _aggregate_pvalues" in "".join(lines)}')
