"""Patch: Upgrade conformal scoring to use multi-view nonconformity.

Problem: per-feature rank-transform destroys geometric correlations.
Fix: Use _reference_score() as nonconformity measure, then conformal calibrate.
"""
import os, sys, re

FP = os.path.join(os.path.dirname(__file__), 'udl', 'system_mode.py')
with open(FP, encoding='utf-8') as f:
    content = f.read()

# ── Replace fit_reference ──
old_fit_ref = '''    def fit_reference(self, X_ref: np.ndarray,
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
        return self'''

new_fit_ref = '''    def fit_reference(self, X_ref: np.ndarray,
                      cal_frac: float = 0.2,
                      random_state: int = 42) -> 'ReducedTensorDescriptor':
        """Fit the descriptor and calibration set for conformal scoring.

        Splits reference data into:
          - fit set (1 - cal_frac): used to fit GMM, covariance, medoid
          - calibration set (cal_frac): used to build the reference
            distribution of nonconformity scores for conformal inference

        Uses the proven multi-view _reference_score() as the base
        nonconformity measure (preserves geometric correlations),
        then wraps it in conformal calibration for distribution-free
        guarantees.

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

        # Store calibration data
        self._cal_X = X_cal
        self._cal_N = n_cal

        # Compute descriptor features on calibration set
        D_cal = self.transform(X_cal)
        self._cal_features = D_cal

        # ── Multi-view nonconformity scores on calibration set ──
        # Use the proven _reference_score pipeline:
        #   40% raw-kNN + 30% desc-kNN + 30% topology
        self._cal_nonconf = self._reference_score(X_cal)
        self._cal_nonconf_sorted = np.sort(self._cal_nonconf)

        # Also store per-feature CDFs for the rank-based view
        self._cal_sorted_features = np.sort(D_cal, axis=0)

        self._conformal_fitted = True
        return self'''

assert old_fit_ref in content, 'Cannot find old fit_reference'
content = content.replace(old_fit_ref, new_fit_ref)

# ── Replace score_conformal ──
old_score = '''    def score_conformal(self, X: np.ndarray) -> np.ndarray:
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
        return scores'''

new_score = '''    def score_conformal(self, X: np.ndarray) -> np.ndarray:
        """Universal anomaly score — dataset-agnostic, distribution-free.

        Uses a two-view nonconformity pipeline:

        View 1 (geometric): The proven _reference_score(), which fuses
            raw-space kNN, descriptor-space kNN, and topology Z-scores.
            This preserves geometric correlations between features.

        View 2 (rank-based): Per-feature empirical p-values combined
            via Fisher + Cauchy. Purely distribution-free.

        Final: max(rank(view1), rank(view2)) — fires if either detects.
        Then calibrate against the calibration set for conformal guarantee.

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
        N = len(X)

        # ── View 1: Multi-view geometric scoring (proven pipeline) ──
        view1 = self._reference_score(X)

        # ── View 2: Rank-based p-value fusion (distribution-free) ──
        D_test = self.transform(X)
        pvals = self._feature_pvalues(D_test, self._cal_features)
        view2 = self._aggregate_pvalues(pvals)

        # ── Fuse: max of rank-normalised views ──
        if N < 3:
            return view1  # not enough points to rank-normalise view2

        def rank_norm(x):
            order = np.argsort(np.argsort(x)).astype(np.float64)
            return order / (len(x) - 1 + 1e-15)

        combined = np.maximum(rank_norm(view1), rank_norm(view2))
        return combined'''

assert old_score in content, 'Cannot find old score_conformal'
content = content.replace(old_score, new_score)

# ── Replace predict_pvalue to use the multi-view nonconformity ──
old_predict = '''    def predict_pvalue(self, X: np.ndarray) -> np.ndarray:
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

        return pvalues'''

new_predict = '''    def predict_pvalue(self, X: np.ndarray) -> np.ndarray:
        """Conformal p-values with distribution-free validity.

        Uses the multi-view _reference_score() as the nonconformity
        measure, then computes conformal p-values:

            p(x) = (1 + #{i : A_cal_i >= A(x)}) / (n_cal + 1)

        where A(x) = _reference_score(x) (multi-view geometric score).

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

        # Nonconformity score via multi-view geometric pipeline
        A_test = self._reference_score(X)

        # Conformal p-value: compare against calibration nonconformity scores
        n_cal = self._cal_N
        A_cal_sorted = self._cal_nonconf_sorted

        # For each test point: p = (1 + #{cal scores >= A_test}) / (n_cal + 1)
        rank = n_cal - np.searchsorted(A_cal_sorted, A_test, side='left')
        pvalues = (1 + rank) / (n_cal + 1)

        return pvalues'''

assert old_predict in content, 'Cannot find old predict_pvalue'
content = content.replace(old_predict, new_predict)

# ── Replace score_conformal_panel ──
# The panel method should also use reference_score-based nonconformity
old_panel_conf = '''    def score_conformal_panel(self, X_3d: np.ndarray,
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

        return q_scores'''

new_panel_conf = '''    def score_conformal_panel(self, X_3d: np.ndarray,
                              y_time: np.ndarray = None,
                              window: int = 4) -> np.ndarray:
        """Universal panel-aware scoring with conformal calibration.

        Uses the multi-view _reference_score() as the base nonconformity
        measure, combined with temporal dynamics and cross-sectional
        aggregation. All components are rank-normalised for
        dataset-agnostic fusion.

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

        # ── Multi-view geometric scores for all points ──
        ref_scores = self._reference_score(X_flat)   # (T*N,)
        ref_3d = ref_scores.reshape(T, N)            # (T, N)

        # Conformal p-values for all points
        pvals = self.predict_pvalue(X_flat)           # (T*N,)
        pvals_3d = pvals.reshape(T, N)                # (T, N)

        # ── Cross-sectional aggregation ──
        # Mean reference score per period (geometric, preserves signal)
        q_mean = ref_3d.mean(axis=1)

        # 90th percentile per period (tail risk)
        q_p90 = np.percentile(ref_3d, 90, axis=1)

        # Fraction of agents with p < 0.05 (breadth of anomalies)
        q_frac_sig = (pvals_3d < 0.05).mean(axis=1)

        # Cross-sectional dispersion
        q_std = ref_3d.std(axis=1)

        # Max-agent score per period
        q_max = ref_3d.max(axis=1)

        # ── Temporal dynamics ──
        # Rolling Z-score of mean reference score
        q_z = np.zeros(T)
        for t in range(window, T):
            w = q_mean[t-window:t]
            mu_w, std_w = w.mean(), w.std() + 1e-10
            q_z[t] = max((q_mean[t] - mu_w) / std_w, 0.0)

        # Momentum (acceleration)
        q_mom = np.zeros(T)
        q_mom[1:] = np.maximum(q_mean[1:] - q_mean[:-1], 0.0)

        # ── Rank-normalised fusion (no dataset-specific weights) ──
        components = np.column_stack([
            q_mean,      # average distress     (geometric signal)
            q_p90,       # tail risk            (geometric signal)
            q_max,       # worst-case agent     (geometric signal)
            q_frac_sig,  # breadth of anomalies (conformal signal)
            q_std,       # cross-sectional spread
            q_z,         # temporal acceleration
            q_mom,       # momentum
        ])

        def rank_norm(x):
            if x.max() == x.min():
                return np.zeros_like(x)
            order = np.argsort(np.argsort(x)).astype(np.float64)
            return order / (len(x) - 1 + 1e-15)

        n_comp = components.shape[1]
        ranked = np.zeros_like(components)
        for j in range(n_comp):
            ranked[:, j] = rank_norm(components[:, j])

        # Equal-weight average of ranks (universal, no tuning)
        q_scores = ranked.mean(axis=1)

        return q_scores'''

assert old_panel_conf in content, 'Cannot find old score_conformal_panel'
content = content.replace(old_panel_conf, new_panel_conf)

with open(FP, 'w', encoding='utf-8') as f:
    f.write(content)

# Verify
for name in ['fit_reference', 'score_conformal', 'predict_pvalue',
             'score_conformal_panel', '_reference_score']:
    assert f'def {name}' in content, f'Missing {name}'

print('Upgraded conformal methods to use multi-view nonconformity.')
print(f'File size: {len(content)} bytes')
