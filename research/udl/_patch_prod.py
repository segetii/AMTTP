"""Patch: Add production-grade scoring to ReducedTensorDescriptor.

Adds:
  1. score_panel()    — panel-aware (T,N,d) scoring with temporal + cross-agent features
  2. fit_score()      — API-compatible with full engines (reference-based scoring)
  3. _reference_score() — kNN + Z-score scoring against reference distribution
"""
import os, sys

FP = os.path.join(os.path.dirname(__file__), 'udl', 'system_mode.py')
with open(FP, encoding='utf-8') as f:
    lines = f.readlines()

joined = ''.join(lines)
if 'def score_panel' in joined:
    print('Already patched.'); sys.exit(0)

print(f'Original lines: {len(lines)}')

# Find the line "    @staticmethod\n" right before _to_scalar
# We know from inspection it's at line 1902 (0-indexed 1901)
insert_idx = None
for i in range(len(lines)-1, 1800, -1):
    if '    @staticmethod' in lines[i] and '_to_scalar' in lines[i+1]:
        insert_idx = i
        break

assert insert_idx is not None, 'Cannot find @staticmethod _to_scalar'
print(f'Inserting before line {insert_idx+1}')

new_methods = r'''    # ═══════════════════════════════════════════════════════════════
    #  PRODUCTION SCORING — real-world-ready methods
    # ═══════════════════════════════════════════════════════════════

    def fit_score(self, X: np.ndarray,
                  y: np.ndarray = None) -> np.ndarray:
        """API-compatible with full engines — reference-based scoring.

        When labels ``y`` are provided (0 = normal, 1 = crisis),
        fits the descriptor on normal-period data and scores all
        points by deviation from that reference distribution.

        When ``y`` is None, fits on all data (unsupervised).

        Parameters
        ----------
        X : (N, d) array — feature matrix (panel-flattened)
        y : (N,) array or None — binary labels (0 = normal)

        Returns
        -------
        scores : (N,) array — anomaly scores (higher = more anomalous)
        """
        X = np.asarray(X, dtype=np.float64)
        if y is not None:
            y = np.asarray(y)
            X_ref = X[y == 0]
        else:
            X_ref = X

        self.fit(X_ref)
        return self._reference_score(X, X_ref)

    def _reference_score(self, X: np.ndarray,
                         X_ref: np.ndarray) -> np.ndarray:
        """Score X by multi-view deviation from reference distribution.

        Mirrors the architecture of ``FusedSystemScorer``:
          1. Transform both X and X_ref through the descriptor
          2. Compute kNN-based deviation in descriptor space
          3. Z-score against reference statistics (positive-deviation only)
          4. Combine with descriptor-native features

        Parameters
        ----------
        X     : (N, d) array — all data points
        X_ref : (N_ref, d) array — normal-period reference points

        Returns
        -------
        scores : (N,) array
        """
        from sklearn.neighbors import NearestNeighbors
        from scipy.spatial.distance import cdist as _cdist

        # 1. Descriptor features for all points and reference
        D_all = self.transform(X)
        D_ref = self.transform(X_ref)

        N = len(X)
        n_eigs = min(self.n_eigs, X.shape[1])

        # 2. kNN deviation in descriptor space
        k = min(10, len(D_ref) - 1)
        if k < 1:
            return self.score(X)

        nn = NearestNeighbors(n_neighbors=k, algorithm='auto')
        nn.fit(D_ref.astype(np.float32))
        dists, _ = nn.kneighbors(D_all.astype(np.float32))

        # Feature 1: mean kNN distance in descriptor space
        knn_mean = dists.mean(axis=1)
        # Feature 2: nearest-neighbor distance (d_1)
        knn_d1 = dists[:, 0]
        # Feature 3: persistence proxy (d_k - d_1) / (d_k + eps)
        knn_persist = (dists[:, -1] - dists[:, 0]) / (dists[:, -1] + 1e-10)

        # Reference statistics for Z-scoring
        ref_dists, _ = nn.kneighbors(D_ref.astype(np.float32))
        ref_mean_d = ref_dists.mean(axis=1)
        mu_ref = ref_mean_d.mean()
        std_ref = ref_mean_d.std() + 1e-10

        # Feature 4: Z-score of kNN distance (positive deviation only)
        z_knn = np.maximum((knn_mean - mu_ref) / std_ref, 0.0)

        # 3. Extract descriptor-native features
        grad_norm   = D_all[:, 0]
        mahalanobis = D_all[:, n_eigs + 1]
        medoid_dist = D_all[:, n_eigs + 2]
        trace_h     = D_all[:, n_eigs + 3]
        morse_idx   = D_all[:, n_eigs + 5].astype(np.float64)

        # Z-score each against reference distribution
        def zpos(vals, ref_vals):
            """Positive-deviation-only Z-score."""
            mu = ref_vals.mean()
            sigma = ref_vals.std() + 1e-10
            return np.maximum((vals - mu) / sigma, 0.0)

        ref_grad = D_ref[:, 0]
        ref_maha = D_ref[:, n_eigs + 1]
        ref_med  = D_ref[:, n_eigs + 2]
        ref_tr   = D_ref[:, n_eigs + 3]
        ref_morse = D_ref[:, n_eigs + 5].astype(np.float64)

        z_grad  = zpos(grad_norm, ref_grad)
        z_maha  = zpos(mahalanobis, ref_maha)
        z_med   = zpos(medoid_dist, ref_med)
        z_trace = zpos(np.abs(trace_h), np.abs(ref_tr))
        z_morse = zpos(morse_idx, ref_morse)

        # 4. Fused score — multi-view weighted combination
        # Weights inspired by MorseTopologyAlarm architecture:
        #   Reference-based kNN features get higher weight (proven discriminative)
        #   Descriptor-native features provide complementary signal
        def robust_norm(x):
            q1, q99 = np.percentile(x, [1, 99])
            xn = (x - q1) / (q99 - q1 + 1e-15)
            return np.clip(xn, 0.0, 1.0)

        # Reference-based view (kNN in descriptor space)
        v_knn = (0.35 * robust_norm(z_knn) +
                 0.30 * robust_norm(knn_d1) +
                 0.20 * robust_norm(knn_persist) +
                 0.15 * robust_norm(knn_mean))

        # Descriptor-native view (Z-scored against reference)
        v_desc = (0.25 * robust_norm(z_grad) +
                  0.30 * robust_norm(z_maha) +
                  0.15 * robust_norm(z_med) +
                  0.10 * robust_norm(z_trace) +
                  0.20 * robust_norm(z_morse))

        # Fuse: 60% reference-based, 40% descriptor (same as FusedSystemScorer)
        scores = 0.60 * v_knn + 0.40 * v_desc
        return scores

    def score_panel(self, X_3d: np.ndarray,
                    y_time: np.ndarray = None,
                    window: int = 4) -> np.ndarray:
        """Panel-aware scoring for (T, N, d) data.

        Designed for real-world financial panel data where:
          - T = number of time steps (quarters)
          - N = number of agents (banks, sectors, grid nodes)
          - d = number of features

        Produces a quarter-level anomaly score that incorporates:
          1. Per-point descriptor features
          2. Cross-sectional statistics (dispersion, skewness across agents)
          3. Temporal dynamics (rolling z-score, momentum)

        Parameters
        ----------
        X_3d   : (T, N, d) array — panel data
        y_time : (T,) array or None — per-quarter labels (0 = normal)
                 If provided, fits on normal quarters only.
        window : int — rolling window for temporal features

        Returns
        -------
        q_scores : (T,) array — quarter-level anomaly scores
        """
        X_3d = np.asarray(X_3d, dtype=np.float64)
        if X_3d.ndim != 3:
            raise ValueError(f'Expected (T, N, d) array, got shape {X_3d.shape}')

        T, N, d = X_3d.shape
        X_flat = X_3d.reshape(T * N, d)

        # Fit on normal-period data
        if y_time is not None:
            y_time = np.asarray(y_time)
            normal_mask = (y_time == 0)
            X_ref = X_3d[normal_mask].reshape(-1, d)
        else:
            # Use first 30% as "calm" reference period
            n_calm = max(1, int(T * 0.3))
            X_ref = X_3d[:n_calm].reshape(-1, d)

        self.fit(X_ref)

        # Compute per-point descriptor features
        D_flat = self.transform(X_flat)       # (T*N, n_eigs+6)
        S_flat = self._reference_score(X_flat, X_ref)  # (T*N,)

        n_eigs = min(self.n_eigs, d)
        D_3d = D_flat.reshape(T, N, -1)       # (T, N, n_eigs+6)
        S_3d = S_flat.reshape(T, N)            # (T, N)

        # ── Per-quarter cross-sectional statistics ──
        # Mean score across agents
        q_mean = S_3d.mean(axis=1)             # (T,)
        # Cross-sectional dispersion (systemic = all agents stressed)
        q_std = S_3d.std(axis=1)               # (T,)
        # Max agent score (worst-case)
        q_max = S_3d.max(axis=1)               # (T,)
        # Fraction of agents with score > 75th percentile of calm
        calm_threshold = np.percentile(S_flat[:len(X_ref)], 75)
        q_frac_high = (S_3d > calm_threshold).mean(axis=1)  # (T,)

        # Cross-sectional Morse index: mean and max
        morse_col_idx = n_eigs + 5
        morse_3d = D_3d[:, :, morse_col_idx]   # (T, N)
        q_morse_mean = morse_3d.mean(axis=1)   # (T,)
        q_morse_max = morse_3d.max(axis=1)     # (T,)

        # Cross-sectional gradient norm dispersion
        grad_3d = D_3d[:, :, 0]                # (T, N)
        q_grad_cv = grad_3d.std(axis=1) / (grad_3d.mean(axis=1) + 1e-10)

        # ── Temporal dynamics ──
        # Rolling Z-score of mean score (Basel III countercyclical buffer style)
        q_z = np.zeros(T)
        for t in range(window, T):
            w = q_mean[t-window:t]
            mu_w, std_w = w.mean(), w.std() + 1e-10
            q_z[t] = (q_mean[t] - mu_w) / std_w
        q_z = np.maximum(q_z, 0)  # positive deviation only

        # Score momentum (first derivative)
        q_mom = np.zeros(T)
        q_mom[1:] = q_mean[1:] - q_mean[:-1]
        q_mom = np.maximum(q_mom, 0)  # rising is concerning

        # Score acceleration (second derivative)
        q_acc = np.zeros(T)
        q_acc[2:] = q_mom[2:] - q_mom[1:-1]
        q_acc = np.maximum(q_acc, 0)

        # ── Fuse all quarter-level features ──
        def rnorm(x):
            q1, q99 = np.percentile(x, [1, 99])
            xn = (x - q1) / (q99 - q1 + 1e-15)
            return np.clip(xn, 0.0, 1.0)

        q_scores = (
            0.20 * rnorm(q_mean) +       # average agent distress
            0.10 * rnorm(q_max) +         # worst-case agent
            0.10 * rnorm(q_frac_high) +   # breadth of distress
            0.10 * rnorm(q_morse_mean) +  # topological signal
            0.05 * rnorm(q_morse_max) +   # worst-case topology
            0.05 * rnorm(q_grad_cv) +     # gradient dispersion
            0.15 * rnorm(q_z) +           # rolling z-score
            0.10 * rnorm(q_mom) +         # momentum
            0.05 * rnorm(q_acc) +         # acceleration
            0.10 * rnorm(q_std)           # cross-sectional spread
        )
        return q_scores

'''

lines[insert_idx:insert_idx] = [new_methods]
print(f'Inserted {new_methods.count(chr(10))} lines')

with open(FP, 'w', encoding='utf-8') as f:
    f.writelines(lines)

total = len(''.join(lines).split('\n'))
print(f'Total lines: {total}')
print(f'fit_score: {"def fit_score" in "".join(lines)}')
print(f'score_panel: {"def score_panel" in "".join(lines)}')
print(f'_reference_score: {"def _reference_score" in "".join(lines)}')
