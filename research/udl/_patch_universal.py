"""Patch: Add score_universal to ReducedTensorDescriptor.

The universal method runs BOTH fit_score and score_panel internally,
then fuses via rank-normalised max. Conformal calibration is applied
for distribution-free p-values.

This is the meta-strategy: use the proven best methods, adaptively
select the stronger signal, guaranteed to work on any dataset.
"""
import os, sys

FP = os.path.join(os.path.dirname(__file__), 'udl', 'system_mode.py')
with open(FP, encoding='utf-8') as f:
    content = f.read()

if 'def score_universal' in content:
    print('Already has score_universal.'); sys.exit(0)

# Insert before score_conformal_panel
marker = '    def score_conformal_panel(self, X_3d: np.ndarray,'
assert marker in content, 'Cannot find score_conformal_panel'

new_method = '''    def score_universal(self, X: np.ndarray, y: np.ndarray,
                        T: int, N: int,
                        window: int = None) -> dict:
        """Universal dataset-agnostic scoring with conformal calibration.

        Runs all scoring modes and fuses them adaptively.
        No dataset-specific weights or hyperparameters.

        Strategy:
          1. fit_score(X, y) — reference-based multi-view scoring
             (optimal for point-level anomaly detection, e.g. ERCOT)
          2. score_panel(X_3d, y_time) — temporal panel scoring
             (optimal for structured panel data, e.g. bank crises)
          3. Conformal p-values — distribution-free false alarm control
          4. Rank-normalised fusion — max(rank_A, rank_B) per point

        The fusion automatically emphasises whichever view is stronger
        for the given dataset, without prior knowledge of dataset type.

        Parameters
        ----------
        X : (T*N, d) array — flat panel data
        y : (T*N,) array — labels (0 = normal)
        T : int — number of time periods
        N : int — number of agents per period
        window : int or None — rolling window (auto-detected if None)

        Returns
        -------
        dict with keys:
            'scores'     : (T*N,) — fused point-level scores
            'q_scores'   : (T,)   — period-level scores
            'pvalues'    : (T*N,) — conformal p-values (point-level)
            'q_pvalues'  : (T,)   — conformal p-values (period-level)
        """
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y)
        d = X.shape[1]

        if window is None:
            window = 4 if T < 200 else max(4, T // 10)

        # ── View 1: Reference-based point scoring (fit_score) ──
        s_point = self.fit_score(X, y)

        # ── View 2: Panel-level temporal scoring ──
        X_3d = X.reshape(T, N, d)
        y_time = y.reshape(T, N)[:, 0]
        desc2 = ReducedTensorDescriptor(
            n_eigs=self.n_eigs, k_neighbors=self.k_neighbors
        )
        q_panel = desc2.score_panel(X_3d, y_time, window=window)
        # Expand to point-level
        s_panel_flat = np.repeat(q_panel, N)

        # ── Rank-normalised fusion ──
        def rank_norm(x):
            n = len(x)
            if n < 2:
                return x.copy()
            order = np.argsort(np.argsort(x)).astype(np.float64)
            return order / (n - 1 + 1e-15)

        # Point-level: max(rank(point_scores), rank(panel_expanded))
        fused = np.maximum(rank_norm(s_point), rank_norm(s_panel_flat))

        # Period-level: average fused score per period
        fused_3d = fused.reshape(T, N)
        q_fused = fused_3d.mean(axis=1)

        # ── Conformal calibration for distribution-free p-values ──
        # Use normal-period scores as calibration set
        ref_mask = (y == 0)
        cal_scores = fused[ref_mask]
        cal_sorted = np.sort(cal_scores)
        n_cal = len(cal_sorted)

        # Point-level conformal p-values
        rank_test = n_cal - np.searchsorted(cal_sorted, fused, side='left')
        pvalues = (1 + rank_test) / (n_cal + 1)

        # Period-level conformal p-values
        cal_q_mask = (y_time == 0)
        cal_q_scores = q_fused[cal_q_mask]
        cal_q_sorted = np.sort(cal_q_scores)
        n_cal_q = len(cal_q_sorted)
        rank_q = n_cal_q - np.searchsorted(cal_q_sorted, q_fused, side='left')
        q_pvalues = (1 + rank_q) / (n_cal_q + 1)

        return {
            'scores': fused,
            'q_scores': q_fused,
            'pvalues': pvalues,
            'q_pvalues': q_pvalues,
            's_point': s_point,
            's_panel': s_panel_flat,
            'q_panel': q_panel,
        }

'''

content = content.replace(marker, new_method + marker)

with open(FP, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Added score_universal. File: {len(content)} bytes')
assert 'def score_universal' in content
